#!/usr/bin/env python3
"""test_report.py — report.py renders both tables and round-trips the run ledger.
No probe, no network: limits reads a fixture usage doc through DELEGATE_CACHE."""
import json, os, shutil, subprocess, sys, tempfile, time
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))

# Run from a fresh directory with no Git root above it, so that
# `catalog.find_git_root()` never finds the invoking checkout's own
# `.delegate/routing.json`. Every path this file needs comes from HERE.
_ISOLATED_CWD = tempfile.TemporaryDirectory(prefix="delegate-test-")
os.chdir(_ISOLATED_CWD.name)
SKILL = os.path.dirname(HERE)
REPORT = os.path.abspath(os.path.join(SKILL, "scripts", "report.py"))
SAMPLES = os.path.abspath(os.path.join(SKILL, "assets", "samples"))
fails = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'} {name}{'' if cond else ': ' + detail}")
    if not cond:
        fails.append(name)


def run(args, env):
    p = subprocess.run([sys.executable, REPORT] + args, capture_output=True, text=True,
                       env={**os.environ, **env})
    return p.returncode, p.stdout, p.stderr


def money(amount):
    q = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${q}"


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def write_dispatch(path, doc):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "dispatch.json"), "w") as f:
        json.dump(doc, f)


with tempfile.TemporaryDirectory() as tmp:
    now = time.time()
    cache = os.path.join(tmp, "usage.json")
    config_dir = os.path.join(tmp, "config")
    shutil.copytree(SAMPLES, config_dir)
    with open(cache, "w") as f:
        json.dump({"probed_at": now, "lanes": [
            {"lane": "agy-gemini", "harness": "agy", "meter": "gemini", "remaining_5h": 0.86,
             "remaining_weekly": 0.88, "r": 0.86, "reset_5h": now + 3600, "reset_weekly": now + 2 * 86400,
             "status": "ok"},
            {"lane": "grok", "harness": "grok", "meter": None, "remaining_5h": None,
             "remaining_weekly": 0.62, "r": 0.62, "reset_5h": None, "reset_weekly": now + 5 * 86400,
             "status": "ok"},
            {"lane": "claude-general", "harness": "claude", "meter": "general", "remaining_5h": 0.89,
             "remaining_weekly": 0.46, "r": 0.46, "reset_5h": now + 3600, "reset_weekly": None, "status": "ok"},
            {"lane": "claude-fable", "harness": "claude", "meter": "fable", "remaining_5h": 0.70,
             "remaining_weekly": 0.30, "r": 0.30, "reset_5h": now + 3600, "reset_weekly": now + 3 * 86400,
             "status": "ok"},
            {"lane": "codex", "harness": "codex", "meter": None, "remaining_5h": 1.0,
             "remaining_weekly": 0.05, "r": 0.05, "reset_5h": now + 3600, "reset_weekly": now + 4 * 86400,
             "status": "unavailable"},
            {"lane": "agy-claude-gpt", "harness": "agy", "meter": "claude-gpt", "remaining_5h": 1.0,
             "remaining_weekly": 0.37, "r": 0.37, "reset_5h": now + 3600, "reset_weekly": now + 2 * 86400,
             "status": "ok"},
        ]}, f)
    env = {"DELEGATE_CACHE": cache, "DELEGATE_RUNS": os.path.join(tmp, "runs.jsonl")}
    cfg = ["--config-dir", config_dir]

    rc, out, err = run(["limits", "--max-age-min", "600"] + cfg, env)
    check("limits exits 0", rc == 0, err)
    header = next((l for l in out.splitlines() if l.startswith("| Lane")), "")
    check("limits header has weekly, 5h, both resets, model, and no binding",
          all(h in header for h in ("Lane", "Model", "Weekly", "5h", "Weekly reset", "5h reset"))
          and "Binding" not in out, header)
    check("weekly and 5h are separate cells",
          "| 88%    | 86%" in out.replace("  ", "  "), out)
    check("a meter with no 5h window renders em dash", "| grok" in out and "—" in out, out)
    check("model comes from the catalog", "gemini-3.8-flash-high" in out, out)
    check("claude meter is named as this session", "this session (all models)" in out, out)
    check("a meter no lane spends is left out of the table",
          "| agy-claude-gpt" not in out, out)
    check("but it is named once, so 37% expiring is not invisible",
          "Ignored, no lane spends them: agy-claude-gpt." in out, out)
    check("missing weekly reset is called out", "Weekly reset unread for: claude-general" in out, out)
    check("weekly reset shows the time left", "(2d)" in out and "(5d)" in out, out)
    limits_body = out.split("**Plan consumption this cycle:**")[0]
    rows = [l for l in limits_body.splitlines() if l.startswith("| ") and not l.startswith("| Lane")]
    check("rows sort by weekly remaining, highest first",
          [r.split("|")[1].strip() for r in rows] ==
          ["agy-gemini", "grok", "claude-general", "claude-fable", "codex"], rows)

    check("plan consumption heading", "**Plan consumption this cycle:**" in out, out)
    plan_body = out.split("**Plan consumption this cycle:**", 1)[1]
    plan_rows = {cells(l)[0]: cells(l) for l in plan_body.splitlines() if l.startswith("| ")
                 and not l.startswith("| Meter")}
    for meter in ("codex", "grok", "agy-gemini", "claude-general", "claude-fable"):
        check(f"plan table has {meter}", meter in plan_rows, str(plan_rows.keys()))
    codex_plan = plan_rows.get("codex", [])
    check("codex plan name and monthly fee",
          len(codex_plan) >= 5 and codex_plan[1] == "ChatGPT Plus" and codex_plan[2] == "$20"
          and codex_plan[3] == "95%", str(codex_plan))
    expected_codex = 20 * 7 / 30.4375 * 0.95
    check("codex plan $ equals weekly slice to the cent",
          len(codex_plan) >= 5 and codex_plan[4] == money(expected_codex), str(codex_plan))
    check("plan footer names the formula",
          "the weekly slice of the monthly fee times the share used" in out, out)

    rc, out, _ = run(["limits", "--max-age-min", "600", "--eligible"] + cfg, env)
    check("--eligible drops a meter under the gate", "| codex" not in out.split(
        "**Plan consumption this cycle:**")[0], out)
    check("--eligible keeps agy whose combined remaining is unknown", "| agy-gemini" in out.split(
        "**Plan consumption this cycle:**")[0], out)
    check("limits footer uses routing.gate not a hard-coded 10%",
          "A meter under 10% remaining is skipped by rank.py." in out, out)

    rc, out, _ = run(["limits", "--max-age-min", "600", "--all"] + cfg, env)
    check("--all brings the ignored meter back", "| agy-claude-gpt" in out
          and "Ignored, no lane" not in out, out)

    rc, out, _ = run(["runs"] + cfg, env)
    check("empty ledger says so", "No runs logged yet." in out, out)

    for args in (["--work", "Ledger A", "--lane", "flash-high@agy", "--secs", "170",
                  "--verdict", "clean", "--batch", "b1"],
                 ["--work", "Ledger finder", "--lane", "grok46@grok", "--secs", "673",
                  "--verdict", "findings", "--outcome", "4 findings, all real", "--batch", "b1"],
                 ["--work", "Stale probe", "--lane", "terra@codex", "--secs", "40",
                  "--verdict", "failed", "--rc", "1", "--status", "blocked", "--batch", "b2"]):
        rc, _, err = run(["log"] + args, env)
        check(f"log {args[1]} exits 0", rc == 0, err)

    lines = [json.loads(l) for l in open(env["DELEGATE_RUNS"])]
    check("one line per log call", len(lines) == 3, str(len(lines)))
    check("record carries v, verdict, batch and an offset timestamp",
          lines[0]["v"] == 1 and lines[0]["verdict"] == "clean" and lines[0]["batch"] == "b1"
          and lines[0]["ts"][-6] in "+-", lines[0])
    check("log without --run has no cost key", "cost" not in lines[0], str(lines[0]))

    rc, out, _ = run(["runs", "--batch", "b1"] + cfg, env)
    check("batch filters the table", "Stale probe" not in out and "Ledger A" in out, out)
    check("clean batch reports rc=0", "2 dispatches, all rc=0, zero failed lanes." in out, out)
    check("wall time is plain seconds", "| 673s" in out, out)
    check("verdict fills an empty outcome", "| clean" in out, out)
    check("roll-up counts minutes and lanes", "~14 minutes" in out and "2 lanes" in out, out)
    check("no-cost records render an em dash", "—" in out, out)

    rc, out, _ = run(["runs"] + cfg, env)
    check("a failed lane changes the head line", "1 needing a second pass" in out, out)

    rc, out, _ = run(["runs", "--last", "1"] + cfg, env)
    check("--last trims to the newest rows", "Ledger A" not in out and "Stale probe" in out, out)

    rc, out, err = run(["log", "--work", "x", "--lane", "y", "--secs", "1", "--verdict", "great"], env)
    check("an unknown verdict is refused", rc != 0, out)

    grok_run = os.path.join(tmp, "run-grok")
    write_dispatch(grok_run, {
        "lane": "grok46-high@grok",
        "usage": {"input_tokens": 120000, "output_tokens": 30000, "cached_tokens": 50000},
        "secs": 300, "status": "done", "thread_id": "t1",
    })
    rc, out, err = run(["log", "--work", "Grok job", "--run", grok_run, "--verdict", "clean"] + cfg, env)
    check("log --run grok exits 0", rc == 0, err)
    check("logged line ends with $0.45", out.strip().endswith("$0.45"), out)
    grok_rec = [json.loads(l) for l in open(env["DELEGATE_RUNS"])][-1]
    gc = grok_rec.get("cost") or {}
    check("grok cost measured", gc.get("measured") is True, str(gc))
    check("grok usd_in 0.24", gc.get("usd_in") == 0.24, str(gc))
    check("grok usd_out 0.18", gc.get("usd_out") == 0.18, str(gc))
    check("grok usd_cache_read 0.025", gc.get("usd_cache_read") == 0.025, str(gc))
    check("grok usd_total 0.445", gc.get("usd_total") == 0.445, str(gc))
    check("grok lane/secs/thread from dispatch",
          grok_rec.get("lane") == "grok46-high@grok" and grok_rec.get("secs") == 300
          and grok_rec.get("thread_id") == "t1" and grok_rec.get("status") == "done", grok_rec)
    rc, out, err = run(["cost", grok_run] + cfg, env)
    check("cost grok exits 0", rc == 0, err)
    check("cost prints grok dollars",
          "0.24" in out and "0.18" in out and "0.025" in out and "0.445" in out, out)

    codex_null = os.path.join(tmp, "run-codex-null")
    write_dispatch(codex_null, {
        "lane": "terra-high@codex", "usage": None, "secs": 12, "status": "done",
    })
    rc, out, err = run(["log", "--work", "Codex null", "--run", codex_null, "--verdict", "clean"] + cfg, env)
    check("log --run null usage exits 0", rc == 0, err)
    check("logged line ends with unmeasured", out.strip().endswith("unmeasured"), out)
    null_rec = [json.loads(l) for l in open(env["DELEGATE_RUNS"])][-1]
    check("null usage stores measured false",
          (null_rec.get("cost") or {}).get("measured") is False, str(null_rec.get("cost")))
    rc, out, _ = run(["runs", "--last", "1"] + cfg, env)
    null_row = next((l for l in out.splitlines() if "Codex null" in l), "")
    check("runs shows unmeasured not $0.00",
          null_row and cells(null_row)[3] == "unmeasured" and "$0.00" not in null_row, out)

    claude_run = os.path.join(tmp, "run-claude")
    write_dispatch(claude_run, {
        "lane": "fable-xhigh@claude",
        "usage": {"input_tokens": 1000, "output_tokens": 2000,
                  "cache_creation_input_tokens": 8000},
        "secs": 9, "status": "done",
    })
    rc, _, err = run(["log", "--work", "Claude write", "--run", claude_run, "--verdict", "clean"] + cfg, env)
    check("log --run claude cache_write exits 0", rc == 0, err)
    claude_rec = [json.loads(l) for l in open(env["DELEGATE_RUNS"])][-1]
    cc = claude_rec.get("cost") or {}
    check("claude cache_write uses lane price",
          cc.get("cache_write_tokens") == 8000 and cc.get("usd_cache_write") == 0.1, str(cc))

    terra_run = os.path.join(tmp, "run-terra")
    write_dispatch(terra_run, {
        "lane": "terra-high@codex",
        "usage": {"input_tokens": 1000000, "output_tokens": 1000,
                  "cache_creation_input_tokens": 4000},
        "secs": 8, "status": "done",
    })
    rc, _, err = run(["log", "--work", "Terra null write", "--run", terra_run, "--verdict", "clean"] + cfg, env)
    check("log --run terra exits 0", rc == 0, err)
    terra_rec = [json.loads(l) for l in open(env["DELEGATE_RUNS"])][-1]
    tc = terra_rec.get("cost") or {}
    check("null cache_write price contributes 0",
          tc.get("usd_cache_write") == 0 and "cache_write" in (tc.get("note") or ""), str(tc))

    mixed_run = os.path.join(tmp, "run-explicit-lane")
    write_dispatch(mixed_run, {
        "lane": "grok46-high@grok",
        "usage": {"input_tokens": 120000, "output_tokens": 30000, "cached_tokens": 50000},
        "secs": 15, "status": "done",
    })
    rc, _, err = run(["log", "--work", "Explicit lane", "--run", mixed_run,
                      "--lane", "luna-low@codex", "--verdict", "clean"] + cfg, env)
    check("log --run explicit --lane exits 0", rc == 0, err)
    exp_rec = [json.loads(l) for l in open(env["DELEGATE_RUNS"])][-1]
    check("explicit --lane wins over dispatch.json",
          exp_rec.get("lane") == "luna-low@codex", exp_rec)
    check("explicit lane prices are used",
          (exp_rec.get("cost") or {}).get("usd_in") == 0.024, str(exp_rec.get("cost")))

    recs = [json.loads(l) for l in open(env["DELEGATE_RUNS"])]
    measured = [r for r in recs if (r.get("cost") or {}).get("measured")]
    n_unm = sum(1 for r in recs if r.get("cost") and not r["cost"].get("measured"))
    usd = sum(r["cost"]["usd_total"] for r in measured)
    rc, out, _ = run(["runs"] + cfg, env)
    check("runs roll-up reports measured total and unmeasured count",
          f"{money(usd)} measured across {len(measured)} runs, {n_unm} unmeasured" in out, out)

    missing = os.path.join(tmp, "no-catalog")
    os.makedirs(missing)
    rc, out, err = run(["limits", "--max-age-min", "600", "--config-dir", missing], env)
    check("limits with a missing catalog exits 1", rc == 1, err)
    check("missing catalog prints report: on stderr", "report:" in err, err)
    check("missing catalog does not print the limits table", "**Current limits:**" not in out, out)

    # statusline tests
    from datetime import datetime
    sl_cache = os.path.join(tmp, "sl_usage.json")
    sl_now = time.time()
    with open(sl_cache, "w") as f:
        json.dump({"probed_at": sl_now, "lanes": [
            {"lane": "agy-gemini", "harness": "agy", "meter": "gemini", "remaining_5h": 0.44,
             "remaining_weekly": 0.68, "r": 0.44, "reset_5h": sl_now + 3 * 3600 + 60,
             "reset_weekly": sl_now + 5 * 86400 + 60, "status": "ok"},
            {"lane": "grok", "harness": "grok", "meter": None, "remaining_5h": None,
             "remaining_weekly": 0.20, "r": 0.20, "reset_5h": None,
             "reset_weekly": sl_now + 4 * 86400 + 60, "status": "ok"},
            {"lane": "codex", "harness": "codex", "meter": None, "remaining_5h": 1.0,
             "remaining_weekly": 0.08, "r": 0.08, "reset_5h": sl_now + 4 * 3600 + 60,
             "reset_weekly": sl_now + 3 * 86400 + 60, "status": "unavailable"},
            {"lane": "claude-general", "harness": "claude", "meter": "general", "remaining_5h": 0.58,
             "remaining_weekly": 0.46, "r": 0.46, "reset_5h": sl_now + 2 * 3600 + 60,
             "reset_weekly": sl_now + 4 * 86400 + 60, "status": "ok"},
            {"lane": "claude-fable", "harness": "claude", "meter": "fable", "remaining_5h": 0.58,
             "remaining_weekly": 0.46, "r": 0.46, "remaining_weekly_model": 0.59,
             "reset_5h": sl_now + 2 * 3600 + 60, "reset_weekly": sl_now + 4 * 86400 + 60, "status": "ok"},
        ]}, f)

    sl_ledger = os.path.join(tmp, "sl_ledger.jsonl")
    with open(sl_ledger, "w") as f:
        # 1. open start inside timeout (flash-high@agy -> tier 1)
        t_in = datetime.fromtimestamp(sl_now - 100).astimezone().isoformat(timespec="seconds")
        f.write(json.dumps({"v": 1, "kind": "dispatch.start", "ts": t_in, "thread_id": "tid-running",
                            "lane": "flash-high@agy", "timeout_s": 600}) + "\n")
        # 2. open start past timeout (terra-high@codex, timeout 300s, started 1000s ago)
        t_stale = datetime.fromtimestamp(sl_now - 1000).astimezone().isoformat(timespec="seconds")
        f.write(json.dumps({"v": 1, "kind": "dispatch.start", "ts": t_stale, "thread_id": "tid-stale",
                            "lane": "terra-high@codex", "timeout_s": 300}) + "\n")
        # 3. start/finish pair (grok46-high@grok)
        t_fin = datetime.fromtimestamp(sl_now - 200).astimezone().isoformat(timespec="seconds")
        f.write(json.dumps({"v": 1, "kind": "dispatch.start", "ts": t_fin, "thread_id": "tid-finished",
                            "lane": "grok46-high@grok", "timeout_s": 600}) + "\n")
        f.write(json.dumps({"v": 1, "kind": "dispatch.finish", "ts": t_fin, "thread_id": "tid-finished",
                            "lane": "grok46-high@grok", "secs": 50, "rc": 0, "status": "done"}) + "\n")

    sl_env = {"DELEGATE_CACHE": sl_cache, "DELEGATE_LEDGER": sl_ledger}
    rc, out, err = run(["statusline", "--no-color"] + cfg, sl_env)
    check("statusline exits 0", rc == 0, err)
    sl_lines = [l for l in out.splitlines() if l.strip()]
    check("statusline prints 5 rows", len(sl_lines) == 5, f"got {len(sl_lines)} lines: {out}")
    labels = [l.split()[1] for l in sl_lines if len(l.split()) > 1]
    check("statusline badged sort first, rest keep catalog order",
          sl_lines[0].startswith("①  agy") and sl_lines[1].startswith("②  grok"), out)
    check("statusline row order has agy first, grok second",
          "agy" in sl_lines[0] and "grok" in sl_lines[1], out)
    check("statusline grok shows em dash for 5h", "grok   5h ·····    —" in sl_lines[1], sl_lines[1])
    check("statusline fable leaves 5h blank", "fable                   wk" in sl_lines[2], sl_lines[2])
    check("statusline unbadged rows start with a placeholder, never a space",
          all(l.startswith("·  ") for l in sl_lines[2:]), out)
    check("statusline fable shows remaining_weekly_model", "59%·4d" in sl_lines[2], sl_lines[2])
    check("statusline codex carries ✗ when gated", "8%·3d✗" in sl_lines[4], sl_lines[4])
    check("statusline running agent shows tier glyph on agy", sl_lines[0].endswith("①"), sl_lines[0])
    check("statusline stale start not in running", not any("③" in l.split("wk")[-1] for l in sl_lines), out)
    check("statusline finished start not in running", not any("②" in sl_lines[1].split("wk")[-1] for l in [sl_lines[1]]), sl_lines[1])

    rc, out_norun, _ = run(["statusline", "--no-color", "--no-running"] + cfg, sl_env)
    check("statusline --no-running drops running glyph", "①" not in out_norun.splitlines()[0].split("wk")[-1], out_norun)

    color_env = dict(sl_env)
    color_env["NO_COLOR"] = ""
    rc, out_color, _ = run(["statusline"] + cfg, color_env)
    check("statusline with color has ANSI escapes", "\033[" in out_color, out_color)

    rc, out_nocache, _ = run(["statusline"] + cfg, {"DELEGATE_CACHE": os.path.join(tmp, "missing_cache.json")})
    check("statusline with missing cache exits 0 and prints nothing", rc == 0 and out_nocache == "", out_nocache)

    sw_env = dict(sl_env, DELEGATE_STATUSLINE_SWITCH=os.path.join(tmp, "sl_switch", "statusline.off"))
    rc, out_st, _ = run(["statusline", "status"] + cfg, sw_env)
    check("statusline status reports on by default", rc == 0 and out_st.strip() == "on", out_st)
    rc, out_off, _ = run(["statusline", "off"] + cfg, sw_env)
    check("statusline off creates the flag file", rc == 0 and os.path.exists(sw_env["DELEGATE_STATUSLINE_SWITCH"]), out_off)
    rc, out_sw, _ = run(["statusline", "--no-color"] + cfg, sw_env)
    check("statusline prints nothing while the switch is off", rc == 0 and out_sw == "", out_sw)
    rc, out_st, _ = run(["statusline", "status"] + cfg, sw_env)
    check("statusline status reports off", out_st.strip() == "off", out_st)
    rc, out_tg, _ = run(["statusline", "toggle"] + cfg, sw_env)
    check("statusline toggle turns the rows back on", out_tg.strip() == "delegate rows on"
          and not os.path.exists(sw_env["DELEGATE_STATUSLINE_SWITCH"]), out_tg)
    rc, out_sw, _ = run(["statusline", "--no-color"] + cfg, sw_env)
    check("statusline prints rows again after toggle", len([l for l in out_sw.splitlines() if l.strip()]) == 5, out_sw)
    rc, out_on, _ = run(["statusline", "on"] + cfg, sw_env)
    check("statusline on is idempotent", rc == 0 and out_on.strip() == "delegate rows on", out_on)

    rc, out_badcat, err_badcat = run(["statusline", "--config-dir", missing], sl_env)
    check("statusline with missing catalog exits 1", rc == 1, err_badcat)
    check("statusline missing catalog prints report: on stderr", "report:" in err_badcat, err_badcat)

    # Gate equality, ignored status, project override, malformed cache, CONSULT_CACHE.
    eq_cache = os.path.join(tmp, "eq_usage.json")
    with open(eq_cache, "w") as f:
        json.dump({"probed_at": now, "lanes": [
            {"lane": "codex", "harness": "codex", "meter": None, "remaining_5h": 0.10,
             "remaining_weekly": 0.10, "r": 0.10, "status": "unavailable",
             "reset_5h": now + 3600, "reset_weekly": now + 4 * 86400},
            {"lane": "grok", "harness": "grok", "meter": None, "remaining_5h": None,
             "remaining_weekly": 0.62, "r": 0.62, "status": "ok",
             "reset_weekly": now + 5 * 86400},
            {"lane": "agy-gemini", "harness": "agy", "meter": "gemini", "remaining_5h": 0.86,
             "remaining_weekly": 0.88, "r": 0.86, "status": "ok",
             "reset_5h": now + 3600, "reset_weekly": now + 2 * 86400},
            {"lane": "claude-general", "harness": "claude", "meter": "general", "remaining_5h": 0.89,
             "remaining_weekly": 0.46, "r": 0.46, "status": "ok",
             "reset_5h": now + 3600, "reset_weekly": now + 4 * 86400},
            {"lane": "claude-fable", "harness": "claude", "meter": "fable", "remaining_5h": 0.58,
             "remaining_weekly": 0.46, "r": 0.46, "remaining_weekly_model": 0.59, "status": "ok",
             "reset_5h": now + 3600, "reset_weekly": now + 4 * 86400},
        ]}, f)
    eq_env = {"DELEGATE_CACHE": eq_cache, "DELEGATE_RUNS": env["DELEGATE_RUNS"]}
    rc, out_eq, _ = run(["limits", "--max-age-min", "600", "--eligible"] + cfg, eq_env)
    check("limits --eligible keeps r equal to gate despite status=unavailable",
          rc == 0 and "| codex" in out_eq.split("**Plan consumption this cycle:**")[0], out_eq)
    rc, out_eq_sl, _ = run(["statusline", "--no-color", "--no-running"] + cfg, eq_env)
    check("statusline does not mark r equal to gate as gated",
          rc == 0 and "✗" not in out_eq_sl, out_eq_sl)

    git_root = os.path.join(tmp, "proj")
    os.makedirs(os.path.join(git_root, ".delegate"))
    open(os.path.join(git_root, ".git"), "w").close()
    with open(os.path.join(git_root, ".delegate", "routing.json"), "w") as f:
        json.dump({"gate": 0.5}, f)
    p = subprocess.run([sys.executable, REPORT, "limits", "--max-age-min", "600", "--eligible",
                        "--config-dir", config_dir],
                       capture_output=True, text=True, cwd=git_root,
                       env={**os.environ, **eq_env})
    proj_body = p.stdout.split("**Plan consumption this cycle:**")[0]
    check("project gate 50% drops r=0.10 from --eligible",
          p.returncode == 0 and "| codex" not in proj_body and "| grok" in proj_body, p.stdout)
    check("project gate footer prints 50%", "under 50% remaining" in p.stdout, p.stdout)

    p_sl = subprocess.run([sys.executable, REPORT, "statusline", "--no-color", "--no-running",
                           "--config-dir", config_dir],
                          capture_output=True, text=True, cwd=git_root,
                          env={**os.environ, **eq_env})
    check("statusline project gate marks r=0.10 with ✗",
          p_sl.returncode == 0 and "✗" in p_sl.stdout, p_sl.stdout)

    bad_cache = os.path.join(tmp, "bad_usage.json")
    with open(bad_cache, "w") as f:
        f.write("{not json")
    rc, out_bad, _ = run(["statusline"] + cfg, {"DELEGATE_CACHE": bad_cache})
    check("statusline with malformed cache exits 0 and prints nothing",
          rc == 0 and out_bad == "", out_bad)

    consult = os.path.join(tmp, "consult_usage.json")
    with open(consult, "w") as f:
        json.dump({"probed_at": now, "lanes": [
            {"lane": "grok", "harness": "grok", "remaining_weekly": 0.99, "r": 0.99,
             "reset_weekly": now + 86400, "status": "ok"},
        ]}, f)
    consult_env = dict(os.environ)
    consult_env.pop("DELEGATE_CACHE", None)
    consult_env["CONSULT_CACHE"] = consult
    p_c = subprocess.run([sys.executable, REPORT, "limits", "--max-age-min", "600"] + cfg,
                         capture_output=True, text=True, env=consult_env)
    check("limits honors CONSULT_CACHE when DELEGATE_CACHE is unset",
          p_c.returncode == 0 and "| grok" in p_c.stdout and "99%" in p_c.stdout,
          p_c.stderr + p_c.stdout)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {', '.join(fails)}"))
sys.exit(1 if fails else 0)
