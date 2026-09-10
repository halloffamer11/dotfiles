#!/usr/bin/env python3
"""test_dispatch.py — tests for delegate.py dispatch path.
Run: python3 tests/test_dispatch.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DELEGATE_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
SAMPLES_DIR = os.path.abspath(os.path.join(HERE, "..", "assets", "samples"))
DELEGATE_PY = os.path.join(DELEGATE_DIR, "delegate.py")
FAKE_RELAY_SRC = os.path.join(HERE, "fake-ads", "relay.mjs")
ADS_SH = os.path.join(DELEGATE_DIR, "ads.sh")


def pinned_ads_commit():
    """The commit ads.sh pins, read from ads.sh itself.

    The fake git below must answer with this, or `ads.sh check` fails every
    dispatch test. Hardcoding it here meant the suite broke on each repin and
    blamed the dispatcher; read it instead so the test follows the pin.
    """
    with open(ADS_SH) as f:
        for line in f:
            if line.startswith("ADS_COMMIT="):
                return line.split("=", 1)[1].strip()
    raise AssertionError(f"no ADS_COMMIT= line in {ADS_SH}")


fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}", file=sys.stderr)


def setup_env(root_dir):
    config_dir = os.path.join(root_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    shutil.copy(os.path.join(SAMPLES_DIR, "lanes.json"), os.path.join(config_dir, "lanes.json"))
    shutil.copy(os.path.join(SAMPLES_DIR, "routing.json"), os.path.join(config_dir, "routing.json"))

    ads_dir = os.path.join(root_dir, "ads")
    for h in ("claude", "codex", "agy", "grok"):
        scripts_dir = os.path.join(ads_dir, "skills", f"{h}-delegate", "scripts")
        os.makedirs(scripts_dir, exist_ok=True)
        shutil.copy(FAKE_RELAY_SRC, os.path.join(scripts_dir, "relay.mjs"))
        os.chmod(os.path.join(scripts_dir, "relay.mjs"), 0o755)

    fake_bin = os.path.join(root_dir, "fake_bin")
    os.makedirs(fake_bin, exist_ok=True)
    git_script = os.path.join(fake_bin, "git")
    with open(git_script, "w") as f:
        f.write('''#!/bin/sh
for arg in "$@"; do
  if [ "$arg" = "HEAD" ]; then
    if [ -n "${ADS_FAKE_GIT_SHA:-}" ]; then
      echo "$ADS_FAKE_GIT_SHA"
    else
      echo "%s"
    fi
    exit 0
  fi
done
exec /usr/bin/git "$@"
''' % pinned_ads_commit())
    os.chmod(git_script, 0o755)

    for h in ("claude", "codex", "agy", "grok"):
        stub = os.path.join(fake_bin, h)
        with open(stub, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(stub, 0o755)

    # Keep real node/sh/python3 reachable without exposing real harness CLIs
    # that share a directory with them (e.g. ~/.local/bin/{node,grok,claude}).
    for tool in ("node", "sh", "python3"):
        src = shutil.which(tool)
        dest = os.path.join(fake_bin, tool)
        if src and not os.path.exists(dest):
            os.symlink(src, dest)

    runs_dir = os.path.join(root_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)

    worktree_dir = os.path.join(root_dir, "worktree")
    os.makedirs(worktree_dir, exist_ok=True)

    ledger_path = os.path.join(root_dir, "ledger.jsonl")
    cache_path = os.path.join(root_dir, "usage.json")

    base_env = dict(os.environ)
    base_env["PATH"] = os.pathsep.join([fake_bin, "/bin", "/usr/bin"])
    base_env["DELEGATE_LEDGER"] = ledger_path
    base_env["DELEGATE_CACHE"] = cache_path
    base_env["ADS_DIR"] = ads_dir

    return {
        "config_dir": config_dir,
        "ads_dir": ads_dir,
        "runs_dir": runs_dir,
        "worktree_dir": worktree_dir,
        "ledger_path": ledger_path,
        "cache_path": cache_path,
        "fake_bin": fake_bin,
        "env": base_env,
    }


def write_stub(t_env, name):
    path = os.path.join(t_env["fake_bin"], name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)


def remove_stub(t_env, name):
    path = os.path.join(t_env["fake_bin"], name)
    if os.path.lexists(path):
        os.remove(path)


def meter(name, weekly=None, five_h=None, pace=None, status="ok", note=None):
    known = [x for x in (five_h, weekly) if x is not None]
    r = min(known) if known else None
    binding = None
    if r is not None:
        binding = "weekly" if (weekly is not None and (five_h is None or weekly <= five_h)) else "5h"
    harness = name.split("-")[0] if "-" in name else name
    meter_sub = name.split("-", 1)[1] if "-" in name else None
    return {
        "lane": name,
        "harness": harness,
        "meter": meter_sub,
        "remaining_5h": five_h,
        "remaining_weekly": weekly,
        "r": r,
        "binding": binding,
        "reset_5h": None,
        "reset_weekly": None,
        "reset_binding": None,
        "cycle_left": None,
        "pace": pace,
        "score": pace if pace is not None else r,
        "status": status,
        "rollover_soon": False,
        "note": note,
    }


def write_meters_doc(path, meters_list):
    doc = {"probed_at": 1700000000, "lanes": meters_list}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    return path


def run_dispatch(t_env, args, extra_env=None):
    env = dict(t_env["env"])
    if extra_env:
        env.update(extra_env)
    cmd = [
        sys.executable,
        DELEGATE_PY,
        "dispatch",
        "--config-dir", t_env["config_dir"],
        "--ads-dir", t_env["ads_dir"],
        "--runs-dir", t_env["runs_dir"],
        "--no-probe",
    ] + args
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def run_run(t_env, args, extra_env=None):
    env = dict(t_env["env"])
    if extra_env:
        env.update(extra_env)
    cmd = [
        sys.executable,
        DELEGATE_PY,
        "run",
        "--config-dir", t_env["config_dir"],
        "--ads-dir", t_env["ads_dir"],
        "--runs-dir", t_env["runs_dir"],
        "--no-probe",
    ] + args
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def parse_run_dir_from_stdout(stdout):
    for line in stdout.splitlines():
        if line.startswith("delegate:") and "run=" in line:
            return line.split("run=")[-1].strip()
    return None


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        t_env = setup_env(tmpdir)
        cwd = t_env["worktree_dir"]

        def make_brief(name, content):
            p = os.path.join(tmpdir, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            return p

        def make_final(name, content):
            p = os.path.join(tmpdir, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            return p

        # -------------------------------------------------------------
        # 1. Completed with a valid done block
        # -------------------------------------------------------------
        done_final = make_final("done_final.json", json.dumps({
            "status": "done",
            "deliverable": "all done deliverable",
            "evidence": [{"file": "test.py", "line": 42, "claim": "it works"}],
            "open_questions": [],
            "changed_files": ["test.py"]
        }))
        b1 = make_brief("b1.md", f"fake-relay: status=completed final={done_final}\nPlease test this.")
        res1 = run_dispatch(t_env, [
            "--lane", "terra-high@codex",
            "--class", "impl",
            "--brief", b1,
            "--cwd", cwd,
        ])
        run_dir1 = parse_run_dir_from_stdout(res1.stdout)
        ok1 = (res1.returncode == 0 and run_dir1 is not None and os.path.isdir(run_dir1))
        if ok1:
            ret1 = json.load(open(os.path.join(run_dir1, "return.json")))
            disp1 = json.load(open(os.path.join(run_dir1, "dispatch.json")))
            ok1 = (
                ret1.get("status") == "done" and
                ret1.get("deliverable") == "all done deliverable" and
                len(ret1.get("evidence", [])) == 1 and
                ret1["evidence"][0]["line"] == 42 and
                disp1.get("secs") is not None and
                disp1.get("session_id") == "fake-thread" and
                set(ret1.keys()) == {"status", "deliverable", "evidence", "open_questions", "changed_files"}
            )
        record("1. completed done block", ok1, f"rc={res1.returncode} stdout={res1.stdout} stderr={res1.stderr}")

        # -------------------------------------------------------------
        # 2a. Completed with partial block
        # -------------------------------------------------------------
        partial_final = make_final("partial_final.json", json.dumps({
            "status": "partial",
            "deliverable": "partially done",
            "evidence": [],
            "open_questions": ["what about edge cases?"],
            "changed_files": []
        }))
        b2a = make_brief("b2a.md", f"fake-relay: status=completed final={partial_final}\nBrief.")
        res2a = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b2a, "--cwd", cwd])
        run_dir2a = parse_run_dir_from_stdout(res2a.stdout)
        ret2a = json.load(open(os.path.join(run_dir2a, "return.json"))) if run_dir2a else {}
        ok2a = (res2a.returncode == 0 and ret2a.get("status") == "partial" and ret2a.get("deliverable") == "partially done")
        record("2a. completed partial block", ok2a, f"rc={res2a.returncode}")

        # -------------------------------------------------------------
        # 2b. Completed with prose and no block -> partial with open question
        # -------------------------------------------------------------
        prose_lines = "\n".join([f"Line {i} of prose without json block" for i in range(70)])
        prose_final = make_final("prose_final.txt", prose_lines)
        b2b = make_brief("b2b.md", f"fake-relay: status=completed final={prose_final}\nBrief.")
        res2b = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b2b, "--cwd", cwd])
        run_dir2b = parse_run_dir_from_stdout(res2b.stdout)
        ret2b = json.load(open(os.path.join(run_dir2b, "return.json"))) if run_dir2b else {}
        ok2b = (
            res2b.returncode == 0 and
            ret2b.get("status") == "partial" and
            len(ret2b.get("deliverable", "").splitlines()) == 60 and
            "no return block in final message" in ret2b.get("open_questions", [])
        )
        record("2b. completed prose no block", ok2b, f"rc={res2b.returncode} oq={ret2b.get('open_questions')}")

        # -------------------------------------------------------------
        # 2c. Completed with empty final -> blocked, exit 1
        # -------------------------------------------------------------
        b2c = make_brief("b2c.md", "fake-relay: status=completed\nNo final file.")
        res2c = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b2c, "--cwd", cwd])
        run_dir2c = parse_run_dir_from_stdout(res2c.stdout)
        ret2c = json.load(open(os.path.join(run_dir2c, "return.json"))) if run_dir2c else {}
        disp2c = json.load(open(os.path.join(run_dir2c, "dispatch.json"))) if run_dir2c else {}
        ok2c = (
            res2c.returncode == 1 and
            ret2c.get("status") == "blocked" and
            disp2c.get("reason") == "empty final message" and
            ret2c.get("deliverable") == "blocked: empty final message"
        )
        record("2c. completed empty final", ok2c, f"rc={res2c.returncode} ret={ret2c}")

        # -------------------------------------------------------------
        # 3. timeout with partial final.txt -> blocked, final.txt preserved
        # -------------------------------------------------------------
        part_txt = make_final("part_text.txt", "Partial progress text before timeout")
        b3 = make_brief("b3.md", f"fake-relay: status=timeout final={part_txt} exit=1\nTimeout brief.")
        res3 = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b3, "--cwd", cwd])
        run_dir3 = parse_run_dir_from_stdout(res3.stdout)
        ret3 = json.load(open(os.path.join(run_dir3, "return.json"))) if run_dir3 else {}
        final_txt_present = os.path.isfile(os.path.join(run_dir3, "final.txt")) if run_dir3 else False
        ok3 = (
            res3.returncode == 1 and
            ret3.get("status") == "blocked" and
            ret3.get("deliverable", "").startswith("blocked: timeout after 25m") and
            final_txt_present
        )
        record("3. timeout with partial final.txt", ok3, f"rc={res3.returncode} deliv={ret3.get('deliverable')}")

        # -------------------------------------------------------------
        # 4. failed with error=boom, aborted, agy_unavailable
        # -------------------------------------------------------------
        b4_fail = make_brief("b4_fail.md", "fake-relay: status=failed error=boom exit=1\nBrief.")
        res4_fail = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b4_fail, "--cwd", cwd])
        run_dir4_fail = parse_run_dir_from_stdout(res4_fail.stdout)
        ret4_fail = json.load(open(os.path.join(run_dir4_fail, "return.json"))) if run_dir4_fail else {}
        ok4a = (res4_fail.returncode == 1 and ret4_fail.get("status") == "blocked" and ret4_fail.get("deliverable") == "blocked: boom")
        record("4a. failed error=boom", ok4a, f"rc={res4_fail.returncode} ret={ret4_fail}")

        b4_abort = make_brief("b4_abort.md", "fake-relay: status=aborted exit=1\nBrief.")
        res4_abort = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b4_abort, "--cwd", cwd])
        run_dir4_abort = parse_run_dir_from_stdout(res4_abort.stdout)
        ret4_abort = json.load(open(os.path.join(run_dir4_abort, "return.json"))) if run_dir4_abort else {}
        ok4b = (res4_abort.returncode == 1 and ret4_abort.get("status") == "blocked")
        record("4b. aborted", ok4b, f"rc={res4_abort.returncode} ret={ret4_abort}")

        b4_unavail = make_brief("b4_unavail.md", "fake-relay: status=agy_unavailable exit=127\nBrief.")
        res4_unavail = run_dispatch(t_env, ["--lane", "flash-high@agy", "--class", "impl", "--brief", b4_unavail, "--cwd", cwd])
        run_dir4_unavail = parse_run_dir_from_stdout(res4_unavail.stdout)
        ret4_unavail = json.load(open(os.path.join(run_dir4_unavail, "return.json"))) if run_dir4_unavail else {}
        disp4_unavail = json.load(open(os.path.join(run_dir4_unavail, "dispatch.json"))) if run_dir4_unavail else {}
        ok4c = (
            res4_unavail.returncode == 1 and
            ret4_unavail.get("status") == "blocked" and
            "unavailable" in disp4_unavail.get("reason", "")
        )
        record("4c. agy_unavailable", ok4c, f"rc={res4_unavail.returncode} reason={disp4_unavail.get('reason')}")

        # -------------------------------------------------------------
        # 5. agy empty reply: status failed, error "Antigravity returned no output"
        # -------------------------------------------------------------
        b5 = make_brief("b5.md", 'fake-relay: status=failed error="Antigravity returned no output" exit=1\nBrief.')
        res5 = run_dispatch(t_env, ["--lane", "flash-high@agy", "--class", "impl", "--brief", b5, "--cwd", cwd])
        run_dir5 = parse_run_dir_from_stdout(res5.stdout)
        ret5 = json.load(open(os.path.join(run_dir5, "return.json"))) if run_dir5 else {}
        ok5 = (
            res5.returncode == 1 and
            ret5.get("status") == "blocked" and
            ret5.get("deliverable") == "blocked: Antigravity returned no output"
        )
        record("5. agy empty reply", ok5, f"rc={res5.returncode} ret={ret5}")

        # -------------------------------------------------------------
        # 6. status=none (no result file)
        # -------------------------------------------------------------
        b6 = make_brief("b6.md", "fake-relay: status=none exit=2\nBrief.")
        res6 = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b6, "--cwd", cwd])
        run_dir6 = parse_run_dir_from_stdout(res6.stdout)
        ret6 = json.load(open(os.path.join(run_dir6, "return.json"))) if run_dir6 else {}
        disp6 = json.load(open(os.path.join(run_dir6, "dispatch.json"))) if run_dir6 else {}
        ok6 = (
            res6.returncode == 1 and
            ret6.get("status") == "blocked" and
            "no result" in disp6.get("reason", "")
        )
        record("6. status=none (no result file)", ok6, f"rc={res6.returncode} reason={disp6.get('reason')}")

        # -------------------------------------------------------------
        # 7. Byte fidelity
        # -------------------------------------------------------------
        raw_brief_bytes = b"\tline with tab\n  trailing spaces   \n- dash bullet\nnon-ascii: \xe2\x98\x83 snowman\nfake-relay: status=completed\n"
        b7_path = os.path.join(tmpdir, "b7_fidelity.md")
        with open(b7_path, "wb") as f:
            f.write(raw_brief_bytes)

        res7 = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b7_path, "--cwd", cwd])
        run_dir7 = parse_run_dir_from_stdout(res7.stdout)
        prompt7_path = os.path.join(run_dir7, "prompt.md") if run_dir7 else None
        brief_copy_path = os.path.join(run_dir7, "brief.txt") if run_dir7 else None

        with open(prompt7_path, "rb") as f:
            prompt_bytes = f.read()
        with open(brief_copy_path, "rb") as f:
            brief_copy_bytes = f.read()

        brief_heading = b"# Brief\n"
        schema_heading = b"# Return schema\n"
        h_idx = prompt_bytes.find(brief_heading)
        s_idx = prompt_bytes.find(schema_heading)
        between_bytes = prompt_bytes[h_idx + len(brief_heading):s_idx].rstrip(b"\n")
        expected_between = raw_brief_bytes.rstrip(b"\n")

        ok7 = (
            between_bytes == expected_between and
            brief_copy_bytes == prompt_bytes
        )
        record("7. byte fidelity", ok7, f"equal={brief_copy_bytes == prompt_bytes}")

        # -------------------------------------------------------------
        # 8. Two dispatches produce two different run directories
        # -------------------------------------------------------------
        b8 = make_brief("b8.md", "fake-relay: status=completed\nBrief 8.")
        res8a = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b8, "--cwd", cwd])
        res8b = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b8, "--cwd", cwd])
        dir8a = parse_run_dir_from_stdout(res8a.stdout)
        dir8b = parse_run_dir_from_stdout(res8b.stdout)
        ok8 = (
            dir8a is not None and dir8b is not None and
            dir8a != dir8b and
            os.path.isdir(dir8a) and os.path.isdir(dir8b)
        )
        record("8. distinct run directories", ok8, f"dir1={dir8a} dir2={dir8b}")

        # -------------------------------------------------------------
        # 9. argv per harness
        # -------------------------------------------------------------
        b9 = make_brief("b9.md", "fake-relay: status=completed\nArgv test.")

        # 9a: terra-high@codex read-only
        res9a = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b9, "--cwd", cwd])
        dir9a = parse_run_dir_from_stdout(res9a.stdout)
        argv9a = json.load(open(os.path.join(dir9a, "argv.json")))
        exp9a = ["--model", "gpt-5.6-terra", "--effort", "high", "--timeout", "25m", "--read-only", "--ignore-user-config", "--skip-git-repo-check"]
        ok9a = all(x in argv9a for x in exp9a)

        # 9b: terra-high@codex with --effort low
        res9b = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b9, "--cwd", cwd, "--effort", "low"])
        dir9b = parse_run_dir_from_stdout(res9b.stdout)
        argv9b = json.load(open(os.path.join(dir9b, "argv.json")))
        ok9b = ("--effort" in argv9b and argv9b[argv9b.index("--effort") + 1] == "low")

        # 9c: terra-high@codex with --write
        res9c = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b9, "--cwd", cwd, "--write", t_env["worktree_dir"]])
        dir9c = parse_run_dir_from_stdout(res9c.stdout)
        argv9c = json.load(open(os.path.join(dir9c, "argv.json")))
        ok9c = ("--read-only" not in argv9c)

        # 9d: flash-high@agy read-only
        res9d = run_dispatch(t_env, ["--lane", "flash-high@agy", "--class", "impl", "--brief", b9, "--cwd", cwd])
        dir9d = parse_run_dir_from_stdout(res9d.stdout)
        argv9d = json.load(open(os.path.join(dir9d, "argv.json")))
        ok9d = ("--print-timeout" in argv9d and argv9d[argv9d.index("--print-timeout") + 1] == "25m" and "--effort" not in argv9d and "--read-only" in argv9d and "--dangerously-skip-permissions" not in argv9d)

        # 9e: flash-high@agy with --write
        res9e = run_dispatch(t_env, ["--lane", "flash-high@agy", "--class", "impl", "--brief", b9, "--cwd", cwd, "--write", t_env["worktree_dir"]])
        dir9e = parse_run_dir_from_stdout(res9e.stdout)
        argv9e = json.load(open(os.path.join(dir9e, "argv.json")))
        ok9e = ("--dangerously-skip-permissions" in argv9e and "--read-only" not in argv9e)

        # 9f: fable-xhigh@claude
        res9f = run_dispatch(t_env, ["--lane", "fable-xhigh@claude", "--class", "impl", "--brief", b9, "--cwd", cwd])
        dir9f = parse_run_dir_from_stdout(res9f.stdout)
        argv9f = json.load(open(os.path.join(dir9f, "argv.json")))
        ok9f = ("--effort" in argv9f and argv9f[argv9f.index("--effort") + 1] == "xhigh" and "--timeout" in argv9f and argv9f[argv9f.index("--timeout") + 1] == "60m")

        # 9g: grok46-high@grok
        res9g = run_dispatch(t_env, ["--lane", "grok46-high@grok", "--class", "impl", "--brief", b9, "--cwd", cwd])
        dir9g = parse_run_dir_from_stdout(res9g.stdout)
        argv9g = json.load(open(os.path.join(dir9g, "argv.json")))
        ok9g = ("--effort" in argv9g and argv9g[argv9g.index("--effort") + 1] == "high" and "--timeout" in argv9g and argv9g[argv9g.index("--timeout") + 1] == "40m")

        # 9h: no argv ever contains --lane, --max-turns, or --max-budget-usd
        all_argvs = [argv9a, argv9b, argv9c, argv9d, argv9e, argv9f, argv9g]
        forbidden = {"--lane", "--max-turns", "--max-budget-usd"}
        ok9h = not any(forbidden.intersection(set(a)) for a in all_argvs)

        ok9 = ok9a and ok9b and ok9c and ok9d and ok9e and ok9f and ok9g and ok9h
        record("9. argv per harness", ok9, f"9a={ok9a} 9b={ok9b} 9c={ok9c} 9d={ok9d} 9e={ok9e} 9f={ok9f} 9g={ok9g} 9h={ok9h}")

        # -------------------------------------------------------------
        # 10. --effort on an agy lane is ignored; proceed with lane effort
        # -------------------------------------------------------------
        b10 = make_brief("b10.md", f"fake-relay: status=completed final={done_final}\nBrief 10.")
        res10 = run_dispatch(t_env, ["--lane", "flash-high@agy", "--class", "impl", "--brief", b10, "--cwd", cwd, "--effort", "low"])
        dir10 = parse_run_dir_from_stdout(res10.stdout)
        ignore_msg = "delegate: effort override ignored on flash-high@agy; agy carries effort in the model name"
        ok10 = (
            res10.returncode == 0 and
            ignore_msg in res10.stderr and
            dir10 is not None
        )
        if ok10:
            disp10 = json.load(open(os.path.join(dir10, "dispatch.json")))
            argv10 = json.load(open(os.path.join(dir10, "argv.json")))
            ok10 = disp10.get("effort") == "high" and "--effort" not in argv10
        record("10. ignore --effort on agy", ok10, f"rc={res10.returncode} err={res10.stderr}")

        # -------------------------------------------------------------
        # 11. Ledger: start and finish events
        # -------------------------------------------------------------
        ledger_path = t_env["ledger_path"]
        if os.path.exists(ledger_path):
            os.remove(ledger_path)
        b11 = make_brief("b11.md", f"fake-relay: status=completed final={done_final}\nBrief 11.")
        res11 = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b11, "--cwd", cwd])
        run_dir11 = parse_run_dir_from_stdout(res11.stdout)
        with open(ledger_path, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        ok11 = (len(lines) == 2)
        if ok11:
            start_ev, fin_ev = lines[0], lines[1]
            ok11 = (
                start_ev.get("v") == 1 and fin_ev.get("v") == 1 and
                start_ev.get("kind") == "dispatch.start" and fin_ev.get("kind") == "dispatch.finish" and
                start_ev.get("thread_id") == fin_ev.get("thread_id") and
                start_ev.get("timeout_s") == 1500 and
                start_ev.get("out") == os.path.join(run_dir11, "return.json") and
                fin_ev.get("status") == "done"
            )
        record("11. ledger start and finish", ok11, f"lines_count={len(lines)} lines={lines}")

        # -------------------------------------------------------------
        # 12. Errors before run dir: unknown lane, relative brief, ads check failure
        # -------------------------------------------------------------
        b12 = make_brief("b12.md", "Brief 12.")
        res12_lane = run_dispatch(t_env, ["--lane", "unknown@codex", "--class", "impl", "--brief", b12, "--cwd", cwd])
        ok12a = (res12_lane.returncode == 2 and "terra-high@codex" in res12_lane.stderr)

        res12_rel = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", "relative.md", "--cwd", cwd])
        ok12b = (res12_rel.returncode == 2)

        runs_before = set(os.listdir(t_env["runs_dir"]))
        res12_ads = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b12, "--cwd", cwd], extra_env={"ADS_FAKE_GIT_SHA": "0000000000000000000000000000000000000000"})
        runs_after = set(os.listdir(t_env["runs_dir"]))
        ok12c = (res12_ads.returncode == 2 and runs_after == runs_before)

        ok12 = ok12a and ok12b and ok12c
        record("12. pre-run errors exit 2 and no run dir", ok12, f"12a={ok12a} 12b={ok12b} 12c={ok12c} ads_err={res12_ads.stderr}")

        # -------------------------------------------------------------
        # 13. readOnlyViolation true -> open_questions carries tripwire line
        # -------------------------------------------------------------
        b13 = make_brief("b13.md", f"fake-relay: status=completed final={done_final} violation=true\nBrief 13.")
        res13 = run_dispatch(t_env, ["--lane", "terra-high@codex", "--class", "impl", "--brief", b13, "--cwd", cwd])
        run_dir13 = parse_run_dir_from_stdout(res13.stdout)
        ret13 = json.load(open(os.path.join(run_dir13, "return.json"))) if run_dir13 else {}
        ok13 = (
            res13.returncode == 0 and
            ret13.get("status") == "done" and
            "read-only tripwire fired; review the diff" in ret13.get("open_questions", [])
        )
        record("13. readOnlyViolation tripwire", ok13, f"rc={res13.returncode} oq={ret13.get('open_questions')}")

        # -------------------------------------------------------------
        # 14. --model gpt-5.6-terra dispatches terra-high@codex
        # -------------------------------------------------------------
        b14 = make_brief("b14.md", f"fake-relay: status=completed final={done_final}\nBrief 14.")
        res14 = run_dispatch(t_env, ["--model", "gpt-5.6-terra", "--class", "impl", "--brief", b14, "--cwd", cwd])
        dir14 = parse_run_dir_from_stdout(res14.stdout)
        ok14 = (res14.returncode == 0 and dir14 is not None)
        if ok14:
            argv14 = json.load(open(os.path.join(dir14, "argv.json")))
            disp14 = json.load(open(os.path.join(dir14, "dispatch.json")))
            ok14 = (
                "--model" in argv14 and argv14[argv14.index("--model") + 1] == "gpt-5.6-terra" and
                disp14.get("lane") == "terra-high@codex"
            )
        record("14. --model gpt-5.6-terra -> terra-high@codex", ok14, f"rc={res14.returncode} stdout={res14.stdout} stderr={res14.stderr}")

        # -------------------------------------------------------------
        # 15. unknown --model lists lanes (with and without --harness)
        # -------------------------------------------------------------
        b15 = make_brief("b15.md", "Brief 15.")
        res15a = run_dispatch(t_env, ["--model", "nope", "--harness", "grok", "--class", "impl", "--brief", b15, "--cwd", cwd])
        ok15a = (
            res15a.returncode == 2 and
            "no lane runs model 'nope' on grok" in res15a.stderr and
            "grok46-high@grok (grok-4.6)" in res15a.stderr
        )
        res15b = run_dispatch(t_env, ["--model", "nope", "--class", "impl", "--brief", b15, "--cwd", cwd])
        expected_lanes = [
            "fable-xhigh@claude (claude-fable-5-1)",
            "sol-high@codex (gpt-5.6-sol)",
            "terra-high@codex (gpt-5.6-terra)",
            "grok46-high@grok (grok-4.6)",
            "luna-low@codex (gpt-5.6-luna)",
            "flash-high@agy (gemini-3.8-flash-high)",
        ]
        ok15b = (
            res15b.returncode == 2 and
            "no lane runs model 'nope'" in res15b.stderr and
            all(item in res15b.stderr for item in expected_lanes)
        )
        record("15. unknown --model lists lanes", ok15a and ok15b, f"15a={ok15a} err_a={res15a.stderr} 15b={ok15b} err_b={res15b.stderr}")

        # -------------------------------------------------------------
        # 16. --lane grok46-high@grok --harness codex mismatch
        # -------------------------------------------------------------
        b16 = make_brief("b16.md", "Brief 16.")
        res16 = run_dispatch(t_env, ["--lane", "grok46-high@grok", "--harness", "codex", "--class", "impl", "--brief", b16, "--cwd", cwd])
        ok16 = (
            res16.returncode == 2 and
            res16.stderr.strip() == "delegate: lane 'grok46-high@grok' runs on grok, not codex"
        )
        record("16. --lane/--harness mismatch", ok16, f"rc={res16.returncode} err={res16.stderr}")

        # -------------------------------------------------------------
        # 17. grok stub removed: PATH error, no run directory
        # -------------------------------------------------------------
        b17 = make_brief("b17.md", "Brief 17.")
        remove_stub(t_env, "grok")
        runs_before17 = set(os.listdir(t_env["runs_dir"]))
        res17 = run_dispatch(t_env, ["--lane", "grok46-high@grok", "--class", "impl", "--brief", b17, "--cwd", cwd])
        runs_after17 = set(os.listdir(t_env["runs_dir"]))
        ok17 = (
            res17.returncode == 2 and
            "grok CLI is not on PATH; install it or pick a lane on another harness" in res17.stderr and
            runs_after17 == runs_before17
        )
        write_stub(t_env, "grok")
        record("17. missing grok CLI, no run dir", ok17, f"rc={res17.returncode} err={res17.stderr}")

        # -------------------------------------------------------------
        # 18. neither --lane nor --model, and both
        # -------------------------------------------------------------
        b18 = make_brief("b18.md", "Brief 18.")
        res18a = run_dispatch(t_env, ["--class", "impl", "--brief", b18, "--cwd", cwd])
        res18b = run_dispatch(t_env, ["--lane", "terra-high@codex", "--model", "gpt-5.6-terra", "--class", "impl", "--brief", b18, "--cwd", cwd])
        ok18 = (res18a.returncode == 2 and res18b.returncode == 2)
        record("18. lane/model required exclusive", ok18, f"rc_a={res18a.returncode} err_a={res18a.stderr} rc_b={res18b.returncode} err_b={res18b.stderr}")

        # -------------------------------------------------------------
        # 19-22. run ranking + dispatch
        # -------------------------------------------------------------
        healthy_meters = write_meters_doc(os.path.join(tmpdir, "healthy_meters.json"), [
            meter("codex", weekly=0.55, five_h=0.55, pace=0.75, status="ok"),
            meter("grok", weekly=1.00, pace=0.90, status="ok"),
            meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
            meter("claude-general", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
            meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
        ])
        b19 = make_brief("b19.md", f"fake-relay: status=completed final={done_final}\nBrief 19.")
        runs_before19 = set(os.listdir(t_env["runs_dir"]))
        res19 = run_run(t_env, ["scout", "--brief", b19, "--cwd", cwd, "--meters", healthy_meters, "--dry-run"])
        runs_after19 = set(os.listdir(t_env["runs_dir"]))
        lines19 = res19.stdout.strip().splitlines()
        ok19 = (
            res19.returncode == 0 and
            any("flash-high@agy" in line and line.endswith("pick") for line in lines19) and
            "delegate: dry run, nothing dispatched" in res19.stdout and
            runs_after19 == runs_before19
        )
        record("19. run scout --dry-run", ok19, f"rc={res19.returncode} stdout={res19.stdout} stderr={res19.stderr}")

        b20 = make_brief("b20.md", f"fake-relay: status=completed final={done_final}\nBrief 20.")
        res20 = run_run(t_env, ["scout", "--brief", b20, "--cwd", cwd, "--meters", healthy_meters])
        dir20 = parse_run_dir_from_stdout(res20.stdout)
        ok20 = (
            res20.returncode == 0 and
            "flash-high@agy" in res20.stdout and
            "delegate: dispatching flash-high@agy" in res20.stdout and
            "delegate:" in res20.stdout and
            "delegate-metrics:" in res20.stdout and
            dir20 is not None and os.path.isdir(dir20)
        )
        if ok20:
            disp20 = json.load(open(os.path.join(dir20, "dispatch.json")))
            ok20 = disp20.get("lane") == "flash-high@agy"
        record("20. run scout dispatches flash-high@agy", ok20, f"rc={res20.returncode} stdout={res20.stdout} stderr={res20.stderr}")

        b21 = make_brief("b21.md", f"fake-relay: status=completed final={done_final}\nBrief 21.")
        res21 = run_run(t_env, ["impl", "--brief", b21, "--cwd", cwd, "--meters", healthy_meters, "--effort", "low"])
        dir21 = parse_run_dir_from_stdout(res21.stdout)
        terra_line = next((ln for ln in res21.stdout.splitlines() if "terra-high@codex" in ln), "")
        ok21 = (
            res21.returncode == 0 and
            "tier=2 trust=5" in terra_line and
            dir21 is not None
        )
        if ok21:
            argv21 = json.load(open(os.path.join(dir21, "argv.json")))
            disp21 = json.load(open(os.path.join(dir21, "dispatch.json")))
            ok21 = (
                "--effort" in argv21 and argv21[argv21.index("--effort") + 1] == "low" and
                disp21.get("effort") == "low"
            )
        record("21. run impl --effort low keeps catalog tier/trust", ok21, f"rc={res21.returncode} terra={terra_line} stderr={res21.stderr}")

        gated_meters = write_meters_doc(os.path.join(tmpdir, "gated_meters.json"), [
            meter("codex", weekly=0.05, five_h=0.05, pace=0.75, status="unavailable"),
            meter("grok", weekly=1.00, pace=0.90, status="ok"),
            meter("claude-fable", weekly=0.70, five_h=0.70, pace=0.85, status="ok"),
            meter("agy-gemini", weekly=0.61, five_h=0.61, pace=3.27, status="ok"),
        ])
        b22 = make_brief("b22.md", "Brief 22.")
        runs_before22 = set(os.listdir(t_env["runs_dir"]))
        res22 = run_run(t_env, ["hard-impl", "--brief", b22, "--cwd", cwd, "--meters", gated_meters, "--harnesses", "codex,agy,grok"])
        runs_after22 = set(os.listdir(t_env["runs_dir"]))
        ok22 = (
            res22.returncode == 1 and
            "STOP: no lane eligible for hard-impl" in res22.stdout and
            runs_after22 == runs_before22
        )
        record("22. run hard-impl STOP no pick", ok22, f"rc={res22.returncode} stdout={res22.stdout} stderr={res22.stderr}")

        # -------------------------------------------------------------
        # 23. run foo -> exit 2 listing classes
        # -------------------------------------------------------------
        b23 = make_brief("b23.md", "Brief 23.")
        res23 = run_run(t_env, ["foo", "--brief", b23, "--cwd", cwd])
        ok23 = (
            res23.returncode == 2 and
            all(c in res23.stderr for c in ("scout", "mechanical", "impl", "review", "hard-impl"))
        )
        record("23. run foo lists classes", ok23, f"rc={res23.returncode} err={res23.stderr}")

        # -------------------------------------------------------------
        # 24. --effort low on flash-high@agy proceeds; argv has no --effort
        # -------------------------------------------------------------
        b24 = make_brief("b24.md", f"fake-relay: status=completed final={done_final}\nBrief 24.")
        res24 = run_dispatch(t_env, ["--lane", "flash-high@agy", "--class", "impl", "--brief", b24, "--cwd", cwd, "--effort", "low"])
        dir24 = parse_run_dir_from_stdout(res24.stdout)
        ok24 = (
            res24.returncode == 0 and
            "delegate: effort override ignored on flash-high@agy; agy carries effort in the model name" in res24.stderr and
            dir24 is not None
        )
        if ok24:
            argv24 = json.load(open(os.path.join(dir24, "argv.json")))
            ok24 = "--effort" not in argv24
        record("24. agy --effort ignored, no argv --effort", ok24, f"rc={res24.returncode} err={res24.stderr}")

    if fails > 0:
        print(f"FAIL: {fails} tests failed", file=sys.stderr)
        sys.exit(1)
    else:
        print("PASS: all test_dispatch.py tests passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
