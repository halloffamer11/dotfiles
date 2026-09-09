#!/usr/bin/env python3
"""test_report.py — report.py renders both tables and round-trips the run ledger.
No probe, no network: limits reads a fixture usage doc through DELEGATE_CACHE."""
import json, os, shutil, subprocess, sys, tempfile, time
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
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
             "remaining_weekly": 0.88, "reset_5h": now + 3600, "reset_weekly": now + 2 * 86400,
             "status": "ok"},
            {"lane": "grok", "harness": "grok", "meter": None, "remaining_5h": None,
             "remaining_weekly": 0.62, "reset_5h": None, "reset_weekly": now + 5 * 86400,
             "status": "ok"},
            {"lane": "claude-general", "harness": "claude", "meter": "general", "remaining_5h": 0.89,
             "remaining_weekly": 0.46, "reset_5h": now + 3600, "reset_weekly": None, "status": "ok"},
            {"lane": "claude-fable", "harness": "claude", "meter": "fable", "remaining_5h": 0.70,
             "remaining_weekly": 0.30, "reset_5h": now + 3600, "reset_weekly": now + 3 * 86400,
             "status": "ok"},
            {"lane": "codex", "harness": "codex", "meter": None, "remaining_5h": 1.0,
             "remaining_weekly": 0.05, "reset_5h": now + 3600, "reset_weekly": now + 4 * 86400,
             "status": "unavailable"},
            {"lane": "agy-claude-gpt", "harness": "agy", "meter": "claude-gpt", "remaining_5h": 1.0,
             "remaining_weekly": 0.37, "reset_5h": now + 3600, "reset_weekly": now + 2 * 86400,
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

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {', '.join(fails)}"))
sys.exit(1 if fails else 0)
