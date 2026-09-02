#!/usr/bin/env python3
"""usage.py — read subscription usage for each installed agent CLI, headlessly.

Emits one JSON document of *lanes* (harness × meter) with an effective
remaining fraction r = min(remaining_5h, remaining_weekly). Costs zero model
tokens: every probe is a slash/status command, not a prompt.

  usage.py            serve cache if younger than TTL, else re-probe
  usage.py --refresh  force re-probe
  usage.py --max-age-min N   override TTL (default 10)
  usage.py --pretty   human table instead of JSON

Cache: $CONSULT_CACHE (default ~/.cache/consult/usage.json).
Absence of a CLI, auth failure, or a probe timeout marks that lane
"unknown" — never a crash. Exit 0 always.
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone

TTL_MIN_DEFAULT = 10
GATE = 0.10           # r below this → lane unavailable
ROLLOVER_MIN = 30     # binding window resets within this → ask user whether to wait
CACHE = os.environ.get("CONSULT_CACHE") or os.path.expanduser("~/.cache/consult/usage.json")
NOW = time.time()

def which(b): return subprocess.run(["command", "-v", b], shell=False, capture_output=True, text=True).returncode == 0 if False else any(os.access(os.path.join(p, b), os.X_OK) for p in os.environ.get("PATH", "").split(os.pathsep))

def run(cmd, timeout=60, stdin_data=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=stdin_data)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

def lane(harness, meter, five_h=None, weekly=None, reset_5h=None, reset_wk=None, note=None):
    """five_h/weekly are REMAINING fractions (0..1) or None; resets are epoch seconds or None."""
    known = [x for x in (five_h, weekly) if x is not None]
    r = min(known) if known else None
    binding = None
    if r is not None:
        binding = "weekly" if (weekly is not None and (five_h is None or weekly <= five_h)) else "5h"
    reset = reset_wk if binding == "weekly" else reset_5h
    status = "unknown" if r is None else ("unavailable" if r < GATE else "ok")
    rollover = bool(reset and status == "unavailable" and (reset - NOW) <= ROLLOVER_MIN * 60)
    return {"lane": f"{harness}-{meter}" if meter else harness, "harness": harness, "meter": meter,
            "remaining_5h": five_h, "remaining_weekly": weekly, "r": r, "binding": binding,
            "reset_5h": reset_5h, "reset_weekly": reset_wk, "reset_binding": reset,
            "status": status, "rollover_soon": rollover, "note": note}

# ---------------------------------------------------------------- codex
def probe_codex():
    if not which("codex"): return [lane("codex", None, note="absent")]
    try:
        p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        def send(o): p.stdin.write(json.dumps(o) + "\n"); p.stdin.flush()
        def recv(i, timeout=20):
            t0 = time.time()
            while time.time() - t0 < timeout:
                line = p.stdout.readline()
                if not line: break
                try: m = json.loads(line)
                except ValueError: continue
                if m.get("id") == i: return m
            return None
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "consult-usage", "version": "0.1"}}})
        if not recv(1): raise RuntimeError("no initialize response")
        send({"method": "initialized"}); time.sleep(0.5)
        send({"id": 2, "method": "account/rateLimits/read", "params": {}})
        m = recv(2)
        p.terminate()
        rl = (m or {}).get("result", {}).get("rateLimits") or {}
        def win(w): return (None, None) if not w else (1 - w["usedPercent"] / 100.0, w.get("resetsAt"))
        # codex labels windows primary/secondary; identify by duration when present
        wins = {}
        for key in ("primary", "secondary"):
            w = rl.get(key)
            if not w: continue
            mins = w.get("windowDurationMins") or 0
            wins["weekly" if mins >= 24 * 60 else "5h"] = win(w)
        f5, r5 = wins.get("5h", (None, None)); fw, rw = wins.get("weekly", (None, None))
        return [lane("codex", None, f5, fw, r5, rw, note=f"plan={rl.get('planType')}")]
    except Exception as e:  # noqa
        return [lane("codex", None, note=f"probe failed: {e}")]

# ---------------------------------------------------------------- agy
def iso(s):
    try: return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception: return None

def probe_agy():
    if not which("agy"): return [lane("agy", None, note="absent")]
    r = run(["agy", "--print", "/usage", "--output-format", "json"], timeout=90, stdin_data="")
    if not r or r.returncode != 0: return [lane("agy", None, note="probe failed")]
    try:
        groups = json.loads(r.stdout)["command"]["data"]["groups"]
    except Exception as e:
        return [lane("agy", None, note=f"unexpected output: {e}")]
    out = []
    for g in groups:
        meter = "gemini" if "gemini" in g["name"].lower() else "claude-gpt"
        f5 = fw = r5 = rw = None
        for b in g.get("buckets", []):
            if b.get("window") == "5h": f5, r5 = b.get("remaining_fraction"), iso(b.get("reset_time", ""))
            elif b.get("window") == "weekly": fw, rw = b.get("remaining_fraction"), iso(b.get("reset_time", ""))
        out.append(lane("agy", meter, f5, fw, r5, rw))
    return out or [lane("agy", None, note="no groups")]

# ---------------------------------------------------------------- claude
def probe_claude():
    if not which("claude"): return [lane("claude", None, note="absent")]
    r = run(["claude", "-p", "--permission-mode", "plan", "--output-format", "json", "/usage"], timeout=60, stdin_data="")
    if not r or r.returncode != 0: return [lane("claude", None, note="probe failed")]
    try: text = json.loads(r.stdout)["result"]
    except Exception as e: return [lane("claude", None, note=f"unexpected output: {e}")]
    def pct(label):
        m = re.search(re.escape(label) + r":\s*(\d+)% used(?: · resets ([^\n]+))?", text)
        return (None, None) if not m else (1 - int(m.group(1)) / 100.0, m.group(2))
    f5, r5 = pct("Current session"); fw, rw = pct("Current week (all models)")
    lanes = [lane("claude", "general", f5, fw, note=f"resets: 5h '{r5}', weekly '{rw}'")]
    # per-model weekly meters, e.g. "Current week (Fable): 86% used"
    for m in re.finditer(r"Current week \(([^)]+)\):\s*(\d+)% used(?: · resets ([^\n]+))?", text):
        name = m.group(1)
        if name.lower() == "all models": continue
        fm = 1 - int(m.group(2)) / 100.0
        wk = min(fw, fm) if fw is not None else fm
        lanes.append(lane("claude", name.lower(), f5, wk, note=f"model-meter weekly {m.group(2)}% used; resets '{m.group(3)}'"))
    return lanes

# ---------------------------------------------------------------- grok
def probe_grok():
    """No headless quota probe exists (1.0.13): /usage is TUI-only and
    `grok -p /usage` is treated as a prompt. Report presence, status unknown."""
    if not which("grok"): return [lane("grok", None, note="absent")]
    v = run(["grok", "--version"], timeout=15, stdin_data="")
    ver = (v.stdout.split()[1] if v and v.stdout.split() else "?")
    return [lane("grok", None, note=f"v{ver}; no headless quota probe — eligible by pin/capability, never balanced")]

# ---------------------------------------------------------------- main
def load_cache(max_age_min):
    try:
        with open(CACHE) as f: d = json.load(f)
        if NOW - d.get("probed_at", 0) <= max_age_min * 60: return d
    except Exception: pass
    return None

def main():
    args = sys.argv[1:]
    refresh = "--refresh" in args; pretty = "--pretty" in args
    ttl = TTL_MIN_DEFAULT
    if "--max-age-min" in args: ttl = float(args[args.index("--max-age-min") + 1])
    d = None if refresh else load_cache(ttl)
    if d is None:
        lanes = probe_codex() + probe_agy() + probe_claude() + probe_grok()
        d = {"probed_at": NOW, "probed_at_iso": datetime.fromtimestamp(NOW, timezone.utc).isoformat(),
             "gate": GATE, "rollover_min": ROLLOVER_MIN, "lanes": lanes}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as f: json.dump(d, f, indent=1)
        d["from_cache"] = False
    else:
        d["from_cache"] = True
    if pretty:
        age = int((NOW - d["probed_at"]) / 60)
        print(f"# usage (cache age {age} min, from_cache={d['from_cache']})")
        for L in d["lanes"]:
            def f(x): return "  ?" if x is None else f"{int(round(x*100)):3d}%"
            rb = L.get("reset_binding")
            rb = datetime.fromtimestamp(rb).strftime("%b %d %H:%M") if rb else "-"
            print(f"{L['lane']:<18} r={f(L['r'])}  5h={f(L['remaining_5h'])}  wk={f(L['remaining_weekly'])}  "
                  f"binding={L['binding'] or '-':<6} reset={rb:<12} {L['status']}"
                  f"{' ROLLOVER-SOON' if L['rollover_soon'] else ''}  {L.get('note') or ''}")
    else:
        print(json.dumps(d, indent=1))

if __name__ == "__main__":
    main()
