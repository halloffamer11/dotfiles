#!/usr/bin/env python3
"""delegate.py — dispatch worker runs through pinned delegate-skills relays.

What a run is:
  A single execution of an external worker on a designated lane (harness × model × effort).
  The worker executes against a specific task brief with either read-only or worktree-write permissions.
  The run manages catalog resolution, prompt assembly, ledger accounting, relay execution,
  and child return normalization.

Run directory layout:
  <runs-dir>/<YYYYMMDDTHHMMSSZ>-<lane>-<8 hex from uuid4>/
    dispatch.json   metadata, configuration, timings, session IDs, and results
    prompt.md       assembled prompt (preamble, cwd, permissions, brief, return schema)
    relay.stdout    raw stdout stream from relay process
    relay.stderr    raw stderr stream from relay process
    result.json     structured outcome from relay
    return.json     normalized child return contract (5 schema fields)
    brief.txt       relay's recorded copy of the brief
    final.txt       child final text (if emitted)
    events.jsonl    child event log (if emitted)

Status mapping:
  completed:
    - with return block (status in done, partial, blocked) -> block status
    - without block, a tool cancelled at the permission gate
      (events.jsonl)                                       -> blocked (reason: permission gate cancelled the run at <tool>)
    - without block and non-empty finalMessage             -> partial (open_question added)
    - with empty finalMessage                              -> blocked (reason: empty final message)
  timeout                                                  -> blocked (reason: timeout after <timeout>)
  failed / aborted / *_unavailable                         -> blocked (reason: error / stderrTail / relay status)
  missing result.json                                      -> blocked (reason: relay wrote no result)
  readOnlyViolation on read-only run                       -> appends tripwire notice to open_questions

CLI:
  python3 delegate.py dispatch (--lane <name> | --model <slug>) [--class <c>] --brief <path> --cwd <dir>
          [--write <worktree>] [--effort <e>] [--harness <h>] [--config-dir DIR]
          [--ads-dir DIR] [--runs-dir DIR] [--no-probe] [--no-leash]
  python3 delegate.py run <class> --brief <path> --cwd <dir> [--write <worktree>] [--tier <n>]
          [--dry-run] [--config-dir DIR] [--meters FILE] [--harnesses a,b,c]
          [--ads-dir DIR] [--runs-dir DIR] [--no-probe] [--no-leash]
"""
import argparse
from datetime import datetime, timezone
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from catalog import load_catalog, CatalogError, HARNESSES, EFFORTS, CLASSES, HARNESS_EFFORTS, meters_enabled
import events
import rank
import usage

# The harness whose lanes run natively, as subagents of the session; a future
# Codex orchestrator changes it (ticket 22, out of scope).
ORCHESTRATOR = "claude"


def parse_timeout_s(timeout_str):
    if not isinstance(timeout_str, str):
        raise ValueError(f"invalid timeout: {timeout_str}")
    if timeout_str.endswith("s"):
        return int(timeout_str[:-1])
    elif timeout_str.endswith("m"):
        return int(timeout_str[:-1]) * 60
    elif timeout_str.endswith("h"):
        return int(timeout_str[:-1]) * 3600
    raise ValueError(f"invalid timeout string: {timeout_str}")


def find_return_block(text, max_candidates=200):
    """Last JSON object in text that parses and carries a status of done, partial,
    or blocked. Scans from the end; bounded so a brace-heavy final message cannot
    turn the scan quadratic."""
    if not text:
        return None
    r_indices = [i for i, c in enumerate(text) if c == "}"][-max_candidates:]
    for end_idx in reversed(r_indices):
        # 1. Balanced depth scan from end_idx backwards
        depth = 0
        candidate_start = None
        for i in range(end_idx, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    candidate_start = i
                    break
        if candidate_start is not None:
            candidate = text[candidate_start:end_idx + 1]
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict) and obj.get("status") in ("done", "partial", "blocked"):
                    return obj
            except Exception:
                pass

        # 2. Check candidate starts before end_idx in reverse
        c_starts = [i for i, c in enumerate(text[:end_idx]) if c == "{"][-max_candidates:]
        for start_idx in reversed(c_starts):
            candidate = text[start_idx:end_idx + 1]
            if "\"status\"" not in candidate and "'status'" not in candidate:
                continue
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict) and obj.get("status") in ("done", "partial", "blocked"):
                    return obj
            except Exception:
                continue

    return None


def _lane_model_listing(lanes, harness=None):
    items = []
    for name in sorted(lanes):
        data = lanes[name]
        if harness is None or data.get("harness") == harness:
            items.append(f"{name} ({data.get('model')})")
    return ", ".join(items)


def resolve(lane_name, class_name, brief_path, cwd_dir, write_dir, effort_arg, config_dir, ads_dir, model_slug=None, harness_filter=None):
    try:
        cat = load_catalog(cwd=cwd_dir, config_dir=config_dir)
    except CatalogError as e:
        sys.stderr.write(f"delegate: {e}\n")
        sys.exit(2)

    lanes = cat.get("lanes", {})

    if model_slug is not None:
        matches = [
            (name, data) for name, data in lanes.items()
            if data.get("model") == model_slug
        ]
        if harness_filter is not None:
            matches = [(n, d) for n, d in matches if d.get("harness") == harness_filter]
        if not matches:
            if harness_filter is not None:
                listing = _lane_model_listing(lanes, harness_filter)
                sys.stderr.write(
                    f"delegate: no lane runs model '{model_slug}' on {harness_filter}; lanes on {harness_filter}: {listing}\n"
                )
            else:
                listing = _lane_model_listing(lanes)
                sys.stderr.write(
                    f"delegate: no lane runs model '{model_slug}'; lanes: {listing}\n"
                )
            sys.exit(2)
        if len(matches) > 1:
            listing = ", ".join(f"{n} ({d.get('harness')})" for n, d in sorted(matches))
            sys.stderr.write(
                f"delegate: model '{model_slug}' matches multiple lanes; pass --harness: {listing}\n"
            )
            sys.exit(2)
        lane_name = matches[0][0]

    if not lane_name or lane_name not in lanes:
        shown = lane_name or ""
        harness = shown.split("@")[-1] if "@" in shown else None
        if harness and harness in HARNESSES:
            avail = [l for l, d in lanes.items() if d.get("harness") == harness]
            if avail:
                sys.stderr.write(f"delegate: unknown lane '{shown}'; available lanes for {harness}: {", ".join(sorted(avail))}\n")
            else:
                sys.stderr.write(f"delegate: unknown lane '{shown}'; available lanes: {", ".join(sorted(lanes.keys()))}\n")
        else:
            sys.stderr.write(f"delegate: unknown lane '{shown}'; available lanes: {", ".join(sorted(lanes.keys()))}\n")
        sys.exit(2)

    lane_data = lanes[lane_name]
    harness = lane_data["harness"]

    if class_name is not None and class_name not in CLASSES:
        sys.stderr.write(f"delegate: invalid class '{class_name}'; must be one of {", ".join(CLASSES)}\n")
        sys.exit(2)

    if not os.path.isabs(brief_path):
        sys.stderr.write(f"delegate: brief path must be absolute: '{brief_path}'\n")
        sys.exit(2)
    if not os.path.isfile(brief_path):
        sys.stderr.write(f"delegate: brief not found: '{brief_path}'\n")
        sys.exit(2)

    if not os.path.isabs(cwd_dir):
        sys.stderr.write(f"delegate: cwd must be an absolute path: '{cwd_dir}'\n")
        sys.exit(2)
    if not os.path.isdir(cwd_dir):
        sys.stderr.write(f"delegate: cwd not a directory: '{cwd_dir}'\n")
        sys.exit(2)

    if write_dir is not None:
        if not os.path.isabs(write_dir):
            sys.stderr.write(f"delegate: write path must be absolute: '{write_dir}'\n")
            sys.exit(2)
        if not os.path.isdir(write_dir):
            sys.stderr.write(f"delegate: write path not a directory: '{write_dir}'\n")
            sys.exit(2)

    child_cwd = write_dir if write_dir else cwd_dir

    if harness_filter is not None and harness != harness_filter:
        sys.stderr.write(f"delegate: lane '{lane_name}' runs on {harness}, not {harness_filter}\n")
        sys.exit(2)

    # An override the lane's harness does not offer is refused, not passed on
    # to a CLI that may silently run something else (ticket 19). An agy
    # override inside agy's list is still only ignored: agy carries the effort
    # in the model name.
    if effort_arg in EFFORTS and effort_arg not in HARNESS_EFFORTS[harness]:
        sys.stderr.write(
            f"delegate: {harness} does not offer effort '{effort_arg}' on {lane_name}; "
            f"{harness} offers {', '.join(HARNESS_EFFORTS[harness])}\n"
        )
        sys.exit(2)
    if harness == "agy" and effort_arg is not None:
        sys.stderr.write(
            f"delegate: effort override ignored on {lane_name}; agy carries effort in the model name\n"
        )
        effort = lane_data["effort"]
    else:
        effort = effort_arg if effort_arg is not None else lane_data["effort"]
    if effort not in EFFORTS:
        sys.stderr.write(f"delegate: invalid effort '{effort}'; must be one of {", ".join(EFFORTS)}\n")
        sys.exit(2)

    if shutil.which(harness) is None:
        sys.stderr.write(
            f"delegate: {harness} CLI is not on PATH; install it or pick a lane on another harness\n"
        )
        sys.exit(2)

    ads_sh = os.path.join(HERE, "ads.sh")
    env = dict(os.environ)
    if ads_dir:
        env["ADS_DIR"] = os.path.abspath(ads_dir)
    proc = subprocess.run(["sh", ads_sh, "check"], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        sys.stderr.write(f"{msg}\n")
        sys.exit(2)

    resolved_ads_dir = os.path.abspath(ads_dir) if ads_dir else (os.environ.get("ADS_DIR") or os.path.expanduser("~/.local/share/delegate/ads"))

    return {
        "lane": lane_name,
        "lane_data": lane_data,
        "harness": harness,
        "model": lane_data["model"],
        "effort": effort,
        "timeout": lane_data["timeout"],
        "child_cwd": child_cwd,
        "ads_dir": resolved_ads_dir,
        "routing": cat.get("routing", {}),
    }


def should_leash(class_name, no_leash=False):
    # The leash sentence is present for scout, mechanical and review, and absent
    # for impl and hard-impl. Review is a reading job bounded by the diff, so it
    # keeps the leash. Impl and hard-impl drop it because the real limit is the
    # lane timeout. --no-leash drops the leash for one job of any class.
    # If class is unspecified, conservative reading is to keep the leash.
    if no_leash:
        return False
    if class_name in ("impl", "hard-impl"):
        return False
    return True


def build_prompt(child_cwd, harness, write_dir, brief_path, run_dir=None, class_=None, no_leash=False):
    preamble_path = os.path.abspath(os.path.join(HERE, "..", "assets", "preamble.md"))
    leash_path = os.path.abspath(os.path.join(HERE, "..", "assets", "preamble-leash.md"))
    schema_path = os.path.abspath(os.path.join(HERE, "..", "assets", "schemas", "return.json"))

    with open(preamble_path, "rb") as f:
        preamble_bytes = f.read()

    leash_active = should_leash(class_, no_leash=no_leash)
    if leash_active:
        with open(leash_path, "rb") as f:
            leash_bytes = f.read().strip()
        anchor = b"no messages. Your final message"
        if anchor not in preamble_bytes:
            # The leash is spliced into the base paragraph at this anchor. Reword
            # preamble.md and the splice would silently drop the sentence, so fail
            # loudly here rather than dispatch a worker with no leash.
            raise RuntimeError(
                f"{preamble_path}: cannot splice the leash: the text "
                f"{anchor.decode()!r} is no longer in the preamble"
            )
        preamble_bytes = preamble_bytes.replace(
            anchor, b"no messages. " + leash_bytes + b" Your final message",
        )

    if not preamble_bytes.endswith(b"\n"):
        preamble_bytes += b"\n"

    if write_dir:
        clause = f"Writes are authorized inside {write_dir} only. Do not commit.\n".encode("utf-8")
    else:
        clause = b"Read-only: do not create, edit, or delete files.\n"

    agy_extra = b""
    if harness == "agy" and not write_dir:
        agy_extra = b"Browser tools are permitted. Terminal commands run inside a sandbox confined to the workspace; you still must not create, edit, or delete files.\n"

    cwd_section = f"\n# Working directory\n{child_cwd}\nEvery relative path in this brief is under it. Do not search elsewhere.\n\n".encode("utf-8")

    brief_heading = b"# Brief\n"

    with open(brief_path, "rb") as f:
        brief_bytes = f.read()

    if brief_bytes.endswith(b"\n"):
        schema_prefix = b"\n# Return schema\nYour final message must end with exactly one JSON object matching this schema, and nothing after it:\n"
    else:
        schema_prefix = b"\n\n# Return schema\nYour final message must end with exactly one JSON object matching this schema, and nothing after it:\n"

    with open(schema_path, "rb") as f:
        schema_bytes = f.read()
    if not schema_bytes.endswith(b"\n"):
        schema_bytes += b"\n"

    prompt_bytes = (
        preamble_bytes +
        clause +
        agy_extra +
        cwd_section +
        brief_heading +
        brief_bytes +
        schema_prefix +
        schema_bytes
    )

    prompt_path = None
    if run_dir is not None:
        prompt_path = os.path.join(run_dir, "prompt.md")
        with open(prompt_path, "wb") as f:
            f.write(prompt_bytes)

    return prompt_bytes, prompt_path


def allocate_run_dir(runs_dir_param, lane, harness, model, effort, timeout, class_name, cwd, write, brief_path, prompt_bytes, leash=True):
    runs_dir = os.path.abspath(os.path.expanduser(runs_dir_param)) if runs_dir_param else os.path.expanduser("~/.cache/delegate/runs")
    os.makedirs(runs_dir, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    thread_id = str(uuid.uuid4())
    hex8 = uuid.uuid4().hex[:8]
    dir_name = f"{stamp}-{lane}-{hex8}"
    run_dir = os.path.join(runs_dir, dir_name)
    os.makedirs(run_dir, exist_ok=False)

    prompt_path = os.path.join(run_dir, "prompt.md")
    with open(prompt_path, "wb") as f:
        f.write(prompt_bytes)

    dispatch_doc = {
        "lane": lane,
        "harness": harness,
        "model": model,
        "effort": effort,
        "timeout": timeout,
        "class": class_name,
        "leash": leash,
        "cwd": cwd,
        "write": write,
        "brief": brief_path,
        "prompt": prompt_path,
        "thread_id": thread_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "relay_status": None,
        "relay_exit": None,
        "secs": None,
        "status": None,
        "reason": None,
        "session_id": None,
        "session": None,
        "usage": None,
        "touched_files": None,
        "read_only_violation": None,
        "finished_at": None,
    }
    with open(os.path.join(run_dir, "dispatch.json"), "w", encoding="utf-8") as f:
        json.dump(dispatch_doc, f, indent=2)
        f.write("\n")

    return run_dir, thread_id, prompt_path


def ledger_start(thread_id, lane, class_name, effort, timeout_str, child_cwd, brief_path, return_path, write_dir):
    timeout_s = parse_timeout_s(timeout_str)
    events.append(events.start_event(
        thread_id=thread_id,
        lane=lane,
        class_=class_name,
        effort=effort,
        timeout_s=timeout_s,
        cwd=child_cwd,
        brief=brief_path,
        out=return_path,
        write=write_dir,
    ))


def probe_meters(no_probe, routing=None):
    if no_probe or (routing is not None and not meters_enabled(routing)):
        return
    usage.acquire(refresh=True, timeout=180)


def codex_home():
    """The delegate-owned CODEX_HOME, or None when this machine has none.

    A codex worker must reach the disposable browser and nothing else that is in
    Orin's own config: no plugins, no Gmail, no codex-cli, no node_repl, no
    hooks, no notify, and not ~/.codex/AGENTS.md, which symlinks his global
    CLAUDE.md. A home of delegate's own holds one MCP server and gives exactly
    that, so a run that finds one drops --ignore-user-config and points codex at
    it. A machine without the home keeps the old isolation, which stays correct
    and has no browser. `make delegate-codex-home` builds it.
    """
    home = os.environ.get("DELEGATE_CODEX_HOME") or os.path.expanduser("~/.local/share/delegate/codex-home")
    return home if os.path.isfile(os.path.join(home, "config.toml")) else None


def run_relay(ads_dir, harness, model, effort, timeout_str, prompt_path, child_cwd, write_dir, run_dir):
    relay_script = os.path.join(ads_dir, "skills", f"{harness}-delegate", "scripts", "relay.mjs")
    env = None
    cmd = [
        "node",
        relay_script,
        "--brief", prompt_path,
        "--cd", child_cwd,
        "--out-dir", run_dir,
        "--model", model,
    ]
    if harness == "claude":
        cmd.extend(["--effort", effort, "--timeout", timeout_str])
        if not write_dir:
            cmd.append("--read-only")
    elif harness == "codex":
        cmd.extend(["--effort", effort, "--timeout", timeout_str, "--skip-git-repo-check"])
        home = codex_home()
        if home:
            env = dict(os.environ)
            env["CODEX_HOME"] = home
        else:
            cmd.append("--ignore-user-config")
        if not write_dir:
            cmd.append("--read-only")
    elif harness == "agy":
        cmd.extend(["--print-timeout", timeout_str])
        if not write_dir:
            cmd.append("--read-only")
        else:
            cmd.append("--dangerously-skip-permissions")
    elif harness == "grok":
        cmd.extend(["--effort", effort, "--timeout", timeout_str])
        if not write_dir:
            cmd.append("--read-only")

    stdout_path = os.path.join(run_dir, "relay.stdout")
    stderr_path = os.path.join(run_dir, "relay.stderr")

    t0 = time.time()
    with open(stdout_path, "wb") as out_f, open(stderr_path, "wb") as err_f:
        proc = subprocess.run(cmd, stdout=out_f, stderr=err_f, env=env)
    secs = int(time.time() - t0)
    relay_exit = proc.returncode

    return relay_exit, secs


def gate_cancelled_tool(run_dir):
    """The tool a permission gate cancelled, if that is how the run ended.

    grok's event stream records a gate refusal as a failed tool_call_update whose
    text says the execution was cancelled, then an end event with
    stopReason=cancelled. Both must hold: a cancel with no cancelled tool is some
    other stop. Returns the tool name ("" if the call was never announced), or
    None when the run did not end at the gate. Other harnesses' event shapes do
    not match and return None.
    """
    events_path = os.path.join(run_dir, "events.jsonl")
    if not os.path.isfile(events_path):
        return None
    tool_names = {}
    cancelled_tool = None
    stop_reason = None
    with open(events_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            kind = ev.get("type")
            if kind == "tool_call":
                tool_names[ev.get("toolCallId")] = ev.get("toolName") or ev.get("title") or ""
            elif kind == "tool_call_update" and ev.get("status") == "failed":
                if "cancel" in json.dumps(ev.get("content")).lower():
                    cancelled_tool = tool_names.get(ev.get("toolCallId"), "")
            elif kind == "end":
                stop_reason = ev.get("stopReason")
    if stop_reason == "cancelled" and cancelled_tool is not None:
        return cancelled_tool
    return None


def map_result(run_dir, lane_timeout, relay_exit, write_dir):
    result_path = os.path.join(run_dir, "result.json")
    stderr_path = os.path.join(run_dir, "relay.stderr")

    status = "blocked"
    reason = None
    deliverable = ""
    evidence = []
    open_questions = []
    changed_files = []
    relay_status = None
    session_id = None
    usage = None
    touched_files = None
    read_only_violation = None

    if not os.path.isfile(result_path):
        last_stderr_line = ""
        if os.path.isfile(stderr_path):
            with open(stderr_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [l.strip() for l in f if l.strip()]
                if lines:
                    last_stderr_line = lines[-1]
        reason = f"relay wrote no result (exit {relay_exit}): {last_stderr_line}".rstrip()
        deliverable = f"blocked: {reason}"
    else:
        try:
            with open(result_path, "r", encoding="utf-8", errors="replace") as f:
                res_doc = json.load(f)
        except Exception as e:
            res_doc = {"status": "failed", "error": f"corrupt result.json: {e}"}

        relay_status = res_doc.get("status")
        session_id = res_doc.get("threadId") or res_doc.get("sessionId") or res_doc.get("conversationId")
        usage = res_doc.get("usage")
        touched_files = res_doc.get("touchedFiles")
        read_only_violation = res_doc.get("readOnlyViolation")
        final_message = res_doc.get("finalMessage") or ""

        if relay_status == "completed":
            block = find_return_block(final_message)
            gated_tool = gate_cancelled_tool(run_dir) if block is None else None
            if block is not None:
                status = block.get("status")
                deliv = block.get("deliverable", "")
                deliverable = deliv if isinstance(deliv, str) else str(deliv)

                ev = block.get("evidence", [])
                if isinstance(ev, list):
                    for item in ev[:12]:
                        if isinstance(item, dict) and "file" in item and "line" in item and "claim" in item:
                            try:
                                evidence.append({
                                    "file": str(item["file"]),
                                    "line": int(item["line"]),
                                    "claim": str(item["claim"])[:200],
                                })
                            except Exception:
                                pass

                oq = block.get("open_questions", [])
                if isinstance(oq, list):
                    for q in oq[:5]:
                        if q is not None:
                            open_questions.append(str(q)[:200])

                cf = block.get("changed_files", [])
                if isinstance(cf, list):
                    for item in cf:
                        if item is not None:
                            changed_files.append(str(item))

                if status == "blocked":
                    reason = deliverable
            elif gated_tool is not None:
                # The relay says completed, but a gated tool was refused and
                # the turn ended there, so the worker did not finish. Reading
                # it as partial hides the cause (ticket 14). As on timeout, the
                # final message stays in final.txt.
                status = "blocked"
                reason = "permission gate cancelled the run"
                if gated_tool:
                    reason += f" at {gated_tool}"
                deliverable = f"blocked: {reason}"
            elif final_message.strip():
                status = "partial"
                deliverable = "\n".join(final_message.splitlines()[:60])
                open_questions = ["no return block in final message"]
            else:
                status = "blocked"
                reason = "empty final message"
                deliverable = f"blocked: {reason}"

        elif relay_status == "timeout":
            status = "blocked"
            reason = f"timeout after {lane_timeout}"
            deliverable = f"blocked: {reason}"

        elif relay_status in ("failed", "aborted") or (isinstance(relay_status, str) and relay_status.endswith("_unavailable")):
            status = "blocked"
            if res_doc.get("error"):
                reason = str(res_doc["error"])
            elif res_doc.get("stderrTail"):
                st = res_doc["stderrTail"]
                reason = "\n".join(st) if isinstance(st, list) else str(st)
            else:
                reason = f"relay status {relay_status}"
            deliverable = f"blocked: {reason}"
        else:
            status = "blocked"
            reason = f"relay status {relay_status}"
            deliverable = f"blocked: {reason}"

        if not write_dir and read_only_violation is True:
            open_questions.append("read-only tripwire fired; review the diff")

    return_doc = {
        "status": status,
        "deliverable": deliverable,
        "evidence": evidence,
        "open_questions": open_questions,
        "changed_files": changed_files,
    }
    return_path = os.path.join(run_dir, "return.json")
    with open(return_path, "w", encoding="utf-8") as f:
        json.dump(return_doc, f, indent=2)
        f.write("\n")

    dispatch_path = os.path.join(run_dir, "dispatch.json")
    if os.path.isfile(dispatch_path):
        with open(dispatch_path, "r", encoding="utf-8") as f:
            dispatch_doc = json.load(f)
        dispatch_doc.update({
            "relay_status": relay_status,
            "relay_exit": relay_exit,
            "secs": None,
            "status": status,
            "reason": reason,
            "session_id": session_id,
            "session": session_id,
            "usage": usage,
            "touched_files": touched_files,
            "read_only_violation": read_only_violation,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        with open(dispatch_path, "w", encoding="utf-8") as f:
            json.dump(dispatch_doc, f, indent=2)
            f.write("\n")

    return {
        "status": status,
        "reason": reason,
        "deliverable": deliverable,
        "evidence": evidence,
        "open_questions": open_questions,
        "changed_files": changed_files,
        "relay_status": relay_status,
        "session_id": session_id,
        "usage": usage,
        "touched_files": touched_files,
        "read_only_violation": read_only_violation,
        "return_path": return_path,
    }


def ledger_finish(thread_id, lane, class_name, secs, relay_exit, status, session_id, return_path):
    events.append(events.finish_event(
        thread_id=thread_id,
        lane=lane,
        class_=class_name,
        secs=secs,
        rc=relay_exit if relay_exit is not None else 1,
        status=status,
        child_session=session_id,
        out=return_path,
    ))


def print_and_exit(lane, status, secs, run_dir, thread_id, class_name, relay_exit):
    class_disp = "-" if class_name is None else class_name
    print(f"delegate: {lane} status={status} secs={secs} run={run_dir}")
    print(f"delegate-metrics: thread={thread_id} status={status} class={class_disp} secs={secs} rc={relay_exit}")
    if status in ("done", "partial"):
        sys.exit(0)
    elif status == "blocked":
        sys.exit(1)
    else:
        sys.exit(1)


def dispatch(lane, class_, brief, cwd, write=None, effort=None, config_dir=None, ads_dir=None, runs_dir=None, no_probe=False, harness=None, model=None, no_leash=False):
    # Step 1: Resolve
    resolved = resolve(
        lane_name=lane,
        class_name=class_,
        brief_path=brief,
        cwd_dir=cwd,
        write_dir=write,
        effort_arg=effort,
        config_dir=config_dir,
        ads_dir=ads_dir,
        model_slug=model,
        harness_filter=harness,
    )
    lane = resolved["lane"]
    harness = resolved["harness"]
    model = resolved["model"]
    eff = resolved["effort"]
    lane_timeout = resolved["timeout"]
    child_cwd = resolved["child_cwd"]
    ads_d = resolved["ads_dir"]

    effective_leash = should_leash(class_, no_leash=no_leash)

    # Step 2: Build the prompt
    prompt_bytes, _ = build_prompt(
        child_cwd=child_cwd,
        harness=harness,
        write_dir=write,
        brief_path=brief,
        class_=class_,
        no_leash=no_leash,
    )

    # Step 3: Allocate the run directory
    run_dir, thread_id, prompt_path = allocate_run_dir(
        runs_dir_param=runs_dir,
        lane=lane,
        harness=harness,
        model=model,
        effort=eff,
        timeout=lane_timeout,
        class_name=class_,
        cwd=cwd,
        write=write,
        brief_path=brief,
        prompt_bytes=prompt_bytes,
        leash=effective_leash,
    )

    if harness == ORCHESTRATOR:
        model_effort = lane.split("@")[0]
        abs_prompt = os.path.abspath(prompt_path)
        print(f"delegate: native lane={lane} agent=lane-{model_effort} prompt={abs_prompt}")
        sys.exit(0)

    return_path = os.path.join(run_dir, "return.json")

    # Step 4: Ledger start
    ledger_start(
        thread_id=thread_id,
        lane=lane,
        class_name=class_,
        effort=eff,
        timeout_str=lane_timeout,
        child_cwd=child_cwd,
        brief_path=brief,
        return_path=return_path,
        write_dir=write,
    )

    # Step 5: Probe meters (before)
    probe_meters(no_probe, resolved.get("routing"))

    # Step 6: Run the relay
    relay_exit, secs = run_relay(
        ads_dir=ads_d,
        harness=harness,
        model=model,
        effort=eff,
        timeout_str=lane_timeout,
        prompt_path=prompt_path,
        child_cwd=child_cwd,
        write_dir=write,
        run_dir=run_dir,
    )

    # Step 5: Probe meters (after)
    probe_meters(no_probe, resolved.get("routing"))

    # Step 7: Map the result
    mapped = map_result(
        run_dir=run_dir,
        lane_timeout=lane_timeout,
        relay_exit=relay_exit,
        write_dir=write,
    )

    # Update secs in dispatch.json
    dispatch_path = os.path.join(run_dir, "dispatch.json")
    if os.path.isfile(dispatch_path):
        with open(dispatch_path, "r", encoding="utf-8") as f:
            d_doc = json.load(f)
        d_doc["secs"] = secs
        with open(dispatch_path, "w", encoding="utf-8") as f:
            json.dump(d_doc, f, indent=2)
            f.write("\n")

    # Step 8: Ledger finish
    ledger_finish(
        thread_id=thread_id,
        lane=lane,
        class_name=class_,
        secs=secs,
        relay_exit=relay_exit,
        status=mapped["status"],
        session_id=mapped["session_id"],
        return_path=return_path,
    )

    # Step 9: Print and exit
    print_and_exit(
        lane=lane,
        status=mapped["status"],
        secs=secs,
        run_dir=run_dir,
        thread_id=thread_id,
        class_name=class_,
        relay_exit=relay_exit,
    )


def run(class_, brief, cwd, write=None, tier=None, dry_run=False, config_dir=None, meters=None, harnesses=None, ads_dir=None, runs_dir=None, no_probe=False, no_leash=False):
    if class_ not in CLASSES:
        sys.stderr.write(f"delegate: invalid class '{class_}'; must be one of {', '.join(CLASSES)}\n")
        sys.exit(2)

    try:
        cat = load_catalog(cwd=cwd, config_dir=config_dir)
    except CatalogError as e:
        sys.stderr.write(f"delegate: {e}\n")
        sys.exit(2)

    cls_config = cat.get("routing", {}).get("classes", {}).get(class_, {})
    floor = cls_config.get("floor")
    ceiling = cls_config.get("ceiling")
    if tier is not None:
        if floor is not None and ceiling is not None and (tier < floor or tier > ceiling):
            sys.stderr.write(
                f"delegate: tier {tier} outside [{floor}, {ceiling}] for class '{class_}'\n"
            )
            sys.exit(2)

    meters_doc = rank.load_usage(cat, meters, refresh=True)

    if harnesses is not None:
        present = set(h.strip() for h in harnesses.split(",") if h.strip())
    else:
        present = {h for h in HARNESSES if shutil.which(h)}

    rows = rank.rank(class_, cat, meters_doc, present, tier=tier)
    has_pick = rank.print_rank_output(class_, cat, rows, tier=tier)
    if not has_pick:
        sys.exit(1)

    if dry_run:
        print("delegate: dry run, nothing dispatched")
        sys.exit(0)

    pick_lane = rows[0]["lane"]
    lane_harness = cat["lanes"][pick_lane]["harness"]
    if lane_harness != ORCHESTRATOR:
        print(f"delegate: dispatching {pick_lane}")
    dispatch(
        lane=pick_lane,
        class_=class_,
        brief=brief,
        cwd=cwd,
        write=write,
        effort=None,
        config_dir=config_dir,
        ads_dir=ads_dir,
        runs_dir=runs_dir,
        no_probe=no_probe,
        no_leash=no_leash,
    )


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(prog="delegate.py", description="Delegate worker dispatcher.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dispatch = sub.add_parser("dispatch", help="dispatch a worker run")
    lane_model = p_dispatch.add_mutually_exclusive_group(required=True)
    lane_model.add_argument("--lane", default=None, help="lane name (e.g. terra-high@codex)")
    lane_model.add_argument("--model", default=None, help="model slug; resolved to a catalog lane")
    p_dispatch.add_argument("--class", dest="class_", default=None, help="work class (e.g. impl)")
    p_dispatch.add_argument("--brief", required=True, help="absolute path to brief file")
    p_dispatch.add_argument("--cwd", required=True, help="working directory")
    p_dispatch.add_argument("--write", default=None, help="writable worktree directory")
    p_dispatch.add_argument("--effort", default=None, help="reasoning effort override")
    p_dispatch.add_argument("--harness", default=None, choices=HARNESSES, help="require the resolved lane to run on this harness")
    p_dispatch.add_argument("--config-dir", default=None, help="directory containing lanes.json and routing.json")
    p_dispatch.add_argument("--ads-dir", default=None, help="directory of amElnagdy/delegate-skills clone")
    p_dispatch.add_argument("--runs-dir", default=None, help="directory where run artifacts are stored")
    p_dispatch.add_argument("--no-probe", action="store_true", help="skip probing usage meters")
    p_dispatch.add_argument("--no-leash", action="store_true", help="drop the 40-tool-call leash for this job")

    p_run = sub.add_parser("run", help="rank and dispatch in one step")
    p_run.add_argument("class_", metavar="class", help="work class")
    p_run.add_argument("--brief", required=True, help="absolute path to brief file")
    p_run.add_argument("--cwd", required=True, help="working directory")
    p_run.add_argument("--write", default=None, help="writable worktree directory")
    p_run.add_argument("--tier", type=int, default=None, help="override floor tier for this job")
    p_run.add_argument("--dry-run", action="store_true", help="print ranking only; do not dispatch")
    p_run.add_argument("--config-dir", default=None, help="directory containing lanes.json and routing.json")
    p_run.add_argument("--meters", default=None, help="path to usage document JSON file")
    p_run.add_argument("--harnesses", default=None, help="comma-separated list of present harnesses")
    p_run.add_argument("--ads-dir", default=None, help="directory of amElnagdy/delegate-skills clone")
    p_run.add_argument("--runs-dir", default=None, help="directory where run artifacts are stored")
    p_run.add_argument("--no-probe", action="store_true", help="skip probing usage meters")
    p_run.add_argument("--no-leash", action="store_true", help="drop the 40-tool-call leash for this job")

    args = parser.parse_args(argv)
    if args.cmd == "dispatch":
        dispatch(
            lane=args.lane,
            class_=args.class_,
            brief=args.brief,
            cwd=args.cwd,
            write=args.write,
            effort=args.effort,
            config_dir=args.config_dir,
            ads_dir=args.ads_dir,
            runs_dir=args.runs_dir,
            no_probe=args.no_probe,
            harness=args.harness,
            model=args.model,
            no_leash=args.no_leash,
        )
    elif args.cmd == "run":
        run(
            class_=args.class_,
            brief=args.brief,
            cwd=args.cwd,
            write=args.write,
            tier=args.tier,
            dry_run=args.dry_run,
            config_dir=args.config_dir,
            meters=args.meters,
            harnesses=args.harnesses,
            ads_dir=args.ads_dir,
            runs_dir=args.runs_dir,
            no_probe=args.no_probe,
            no_leash=args.no_leash,
        )


if __name__ == "__main__":
    main()
