#!/usr/bin/env python3
"""usage.py — read subscription usage for each installed agent CLI, headlessly.

Emits one JSON document of *lanes* (harness × meter). Per lane:
  r      = min(remaining_5h, remaining_weekly): the gate (availability).
           Every meter with two windows is read this way, agy included; no
           vendor publishes a joint bound, so agy carries a note saying the
           combined figure is the lower window, an assumption (ticket 31).
  pace   = remaining_weekly / fraction of the weekly cycle still to run.
           1.0 = spending evenly; >1 = ahead (under-used, will expire unspent);
           <1 = behind (over-spent). Cycle length is assumed 7 days.
  score  = pace when the weekly meter and its reset are known, else r.
           rank.py sorts on pace. The 5h window is a rate cap, not a budget:
           what expires unspent is the weekly allotment, so pace is the thing
           to balance.

Codex, agy, and grok probes are status/RPC commands. The Claude probe runs
`claude -p /usage` and can spend the meter being measured.

  usage.py            serve cache if younger than TTL, else re-probe
  usage.py --refresh  force re-probe
  usage.py --max-age-min N   override TTL (default 10)
  usage.py --pretty   human table instead of JSON

Cache: get_cache_path() — $DELEGATE_CACHE, else $CONSULT_CACHE, else
~/.cache/delegate/usage.json. Absence of a CLI, auth failure, or a probe
timeout marks that lane "unknown" — never a crash. Exit 0 always.

Public acquisition: load_cached() never probes and never writes a meter
event; probe(refresh=...) is the refresh/TTL path.
"""
import json, math, os, re, subprocess, sys, time
from datetime import datetime, timezone
try:
    from events import append, meter_event
except ImportError:
    from .events import append, meter_event

TTL_MIN_DEFAULT = 10
WEEK = 7 * 86400      # assumed weekly-cycle length for pace
CYCLE_FLOOR = 0.02    # ~3.4h: pace denominator floor near a reset
ROLLOVER_MIN = 30     # binding window resets within this → ask user whether to wait
AGY_COMBINED_NOTE = ("agy combined remaining is the lower window, an assumption, "
                     "not a vendor bound")
# The note the reversed rule wrote (modular ticket 13). A cache from that time
# still carries it beside null figures; a read replaces both together.
SUPERSEDED_AGY_NOTE = "agy combined remaining and pace unknown until a vendor joint bound exists"

def get_cache_path():
    return os.environ.get("DELEGATE_CACHE") or os.environ.get("CONSULT_CACHE") or os.path.expanduser("~/.cache/delegate/usage.json")
CACHE = get_cache_path()

def _valid_meter_number(value, *, fraction=False):
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        number = float(value)
    except OverflowError:
        return False
    return math.isfinite(number) and (0 <= number <= 1 if fraction else number >= 0)


def combined(five_h, weekly, reset_5h=None, reset_wk=None):
    """The figures every Meter derives from its raw Window values.

    Remaining is the lower of the Window fractions, and Pace divides the weekly
    fraction by the share of the week still to run. One arithmetic for every
    harness: agy has a 5-hour and a weekly Window like the Claude Meters, so it
    is read the same way (ticket 31).
    """
    known = [x for x in (five_h, weekly) if x is not None]
    r = min(known) if known else None
    binding = None
    if r is not None:
        binding = "weekly" if (weekly is not None and (five_h is None or weekly <= five_h)) else "5h"
    reset = reset_wk if binding == "weekly" else reset_5h
    cycle_left = pace = None
    if weekly is not None and reset_wk:
        cycle_left = min(1.0, max(CYCLE_FLOOR, (reset_wk - time.time()) / WEEK))
        pace = round(weekly / cycle_left, 3)
    return {"r": r, "binding": binding, "reset_binding": reset,
            "cycle_left": cycle_left, "pace": pace,
            "score": pace if pace is not None else r,
            # Observation quality is independent of a project's effective Gate.
            "status": "unknown" if r is None else "ok"}


def _filled(observation):
    """Derive the combined figures a cache is missing. Never overwrites one.

    A cache written while agy figures were forced unknown holds the Windows
    beside a null Remaining and Pace. Reading it derives them by the same
    arithmetic a probe uses, so the figures need no fresh probe. An observation
    that already carries a Remaining or a Pace is returned untouched, and one
    with no Window at all stays unknown.
    """
    if not isinstance(observation, dict):
        return observation
    if observation.get("r") is not None or observation.get("pace") is not None:
        return observation
    if observation.get("remaining_5h") is None and observation.get("remaining_weekly") is None:
        return observation
    out = dict(observation)
    out.update(combined(out.get("remaining_5h"), out.get("remaining_weekly"),
                        out.get("reset_5h"), out.get("reset_weekly")))
    note = out.get("note")
    if note and SUPERSEDED_AGY_NOTE in str(note):
        out["note"] = str(note).replace(SUPERSEDED_AGY_NOTE, AGY_COMBINED_NOTE)
    return out


def _fill_document(document):
    """Return a copy whose observations carry their combined figures. Does not write."""
    if not isinstance(document, dict):
        return document
    out = dict(document)
    if "lanes" in out and isinstance(out["lanes"], list):
        out["lanes"] = [_filled(entry) for entry in out["lanes"]]
        return out
    return {name: _filled(obs) for name, obs in out.items()}


def observations(document):
    """Return validated observations by Meter, or None for a malformed document.

    Accept the usage-cache envelope and the legacy bare Meter map. Invalid
    observations make the whole document unknown, consistently for every caller.
    No Window value is repaired and this boundary never probes a vendor; a
    combined figure a cache never wrote is derived from the Windows (`_filled`).
    """
    if not isinstance(document, dict):
        return None
    if "lanes" in document:
        if document.get("probed_at") is None or not _valid_meter_number(document["probed_at"]):
            return None
        if not isinstance(document["lanes"], list):
            return None
        parsed = {}
        for entry in document["lanes"]:
            if not isinstance(entry, dict):
                return None
            name = entry.get("lane")
            if not isinstance(name, str) or not name:
                return None
            parsed[name] = entry
        entries = [(entry["lane"], entry) for entry in document["lanes"]]
    else:
        parsed = document
        entries = document.items()
    for name, observation in entries:
        if not isinstance(name, str) or not name or not isinstance(observation, dict):
            return None
        if not _valid_meter_number(observation.get("r"), fraction=True):
            return None
        if not _valid_meter_number(observation.get("pace")):
            return None
        for field in ("remaining_weekly", "remaining_5h", "remaining_weekly_model"):
            if not _valid_meter_number(observation.get(field), fraction=True):
                return None
        for field in ("reset_5h", "reset_weekly", "reset_binding"):
            if not _valid_meter_number(observation.get(field)):
                return None
        if "status" in observation and not isinstance(observation["status"], str):
            return None
    return {name: _filled(observation) for name, observation in parsed.items()}


def eligible(observation, gate):
    """Unknown Remaining never vetoes; Remaining equal to Gate is eligible."""
    if not observation or not isinstance(observation, dict):
        return True
    r = observation.get("r")
    if r is None:
        return True
    try:
        return float(r) >= float(gate)
    except (TypeError, ValueError, OverflowError):
        return True


def load_cached(cache_path=None):
    """Read the usage cache without probing or emitting a meter event.

    Missing or unreadable files become {}. A combined Remaining or Pace the
    cache lacks is derived in the returned copy; the file on disk is not
    rewritten.
    """
    path = cache_path or get_cache_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc, dict) or observations(doc) is None:
            return {}
        return _fill_document(doc)
    except (OSError, ValueError):
        return {}

def which(b): return subprocess.run(["command", "-v", b], shell=False, capture_output=True, text=True).returncode == 0 if False else any(os.access(os.path.join(p, b), os.X_OK) for p in os.environ.get("PATH", "").split(os.pathsep))

def run(cmd, timeout=60, stdin_data=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=stdin_data)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

def lane(harness, meter, five_h=None, weekly=None, reset_5h=None, reset_wk=None, note=None, remaining_weekly_model=None):
    """five_h/weekly are REMAINING fractions (0..1) or None; resets are epoch seconds or None."""
    row = {"lane": f"{harness}-{meter}" if meter else harness, "harness": harness, "meter": meter,
           "remaining_5h": five_h, "remaining_weekly": weekly,
           "remaining_weekly_model": remaining_weekly_model,
           "reset_5h": reset_5h, "reset_weekly": reset_wk,
           "rollover_soon": False, "note": note}
    row.update(combined(five_h, weekly, reset_5h, reset_wk))
    return row

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
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "delegate-usage", "version": "0.1"}}})
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
        # No vendor bound joins the two windows, so the note says what the
        # combined figure is: the lower window, an assumption (ticket 31).
        out.append(lane("agy", meter, f5, fw, r5, rw, note=AGY_COMBINED_NOTE))
    return out or [lane("agy", None, note="no groups")]

# ---------------------------------------------------------------- claude
def claude_reset(text):
    """'Sep 8 at 2:59pm (America/New_York)' -> epoch seconds, or None. The year is
    not printed: assume the current one, roll forward if that lands in the past."""
    if not text: return None
    m = re.search(r"([A-Z][a-z]{2}) (\d{1,2}) at (\d{1,2})(?::(\d{2}))?(am|pm) \(([^)]+)\)", text)
    if not m: return None
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(m.group(6)); hour = int(m.group(3)) % 12 + (12 if m.group(5) == "pm" else 0)
        minute = m.group(4) or "00"
        year = datetime.now(tz).year
        t = datetime.strptime(f"{m.group(1)} {m.group(2)} {year} {hour}:{minute}", "%b %d %Y %H:%M").replace(tzinfo=tz)
        if t.timestamp() < time.time() - 86400: t = t.replace(year=year + 1)
        return t.timestamp()
    except Exception:
        return None

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
    lanes = [lane("claude", "general", f5, fw, claude_reset(r5), claude_reset(rw),
                  note=f"resets: 5h '{r5}', weekly '{rw}'")]
    # per-model weekly meters, e.g. "Current week (Fable): 86% used"
    for m in re.finditer(r"Current week \(([^)]+)\):\s*(\d+)% used(?: · resets ([^\n]+))?", text):
        name = m.group(1)
        if name.lower() == "all models": continue
        fm = 1 - int(m.group(2)) / 100.0
        wk = min(fw, fm) if fw is not None else fm
        lanes.append(lane("claude", name.lower(), f5, wk, claude_reset(r5), claude_reset(m.group(3) or rw),
                          note=f"model-meter weekly {m.group(2)}% used; resets '{m.group(3)}'",
                          remaining_weekly_model=fm))
    return lanes

# ---------------------------------------------------------------- grok
def probe_grok():
    """Weekly meter via the Agent Client Protocol: `grok agent stdio`, then the
    `_x.ai/billing` extension method (what the TUI's /usage dialog calls). Zero
    model tokens. Payload fields (serde list in the binary, 1.0.13):
    creditUsagePercent, currentPeriod{type,start,end}, includedUsed, totalUsed,
    monthlyLimit, onDemandCap/Used, prepaidBalance, subscription_tier. Zero-valued
    fields are omitted, so a missing creditUsagePercent means 0% used."""
    if not which("grok"): return [lane("grok", None, note="absent")]
    try:
        p = subprocess.Popen(["grok", "agent", "stdio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        def send(i, method, params):
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n"); p.stdin.flush()
        def recv(i, timeout=25):
            t0 = time.time()
            while time.time() - t0 < timeout:
                line = p.stdout.readline()
                if not line: break
                try: m = json.loads(line)
                except ValueError: continue
                if m.get("id") == i: return m
            return None
        send(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
                                "_meta": {"clientType": "delegate-usage", "clientVersion": "0.1"}})
        if not recv(1): raise RuntimeError("no initialize response")
        send(2, "_x.ai/billing", {})
        m = recv(2)
        p.terminate()
        if not m or "result" not in m: raise RuntimeError(f"billing: {(m or {}).get('error')}")
        res = m["result"]; cfg = res.get("config") or {}
        pct = cfg.get("creditUsagePercent")
        if isinstance(pct, dict): pct = pct.get("val")
        pct = float(pct or 0)
        period = cfg.get("currentPeriod") or {}
        end = iso(period.get("end") or cfg.get("billingPeriodEnd") or "")
        ptype = (period.get("type") or "").replace("USAGE_PERIOD_TYPE_", "").lower() or "weekly"
        tier = res.get("subscription_tier")
        # single rolling meter (weekly on SuperGrok); no 5h window exists
        return [lane("grok", None, None, 1 - pct / 100.0, None, end,
                     note=f"tier={tier}; {ptype} meter only ({pct:g}% used); via _x.ai/billing")]
    except Exception as e:  # noqa
        try: p.terminate()
        except Exception: pass
        return [lane("grok", None, note=f"probe failed: {e}")]

# ---------------------------------------------------------------- main
def load_cache(max_age_min, cache_path=None):
    p = cache_path or get_cache_path()
    try:
        with open(p) as f: d = json.load(f)
        if (isinstance(d, dict) and "lanes" in d and observations(d) is not None
                and _valid_meter_number(d.get("probed_at"))
                and d.get("probed_at") is not None
                and 0 <= time.time() - d["probed_at"] <= max_age_min * 60):
            return d
    except Exception: pass
    return None

def write_cache(d, cache_path=None):
    p = cache_path or get_cache_path()
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(p, "w") as f:
        json.dump(d, f, indent=1)
    append(meter_event(d))

def probe(refresh=False, max_age_min=None, cache_path=None):
    """Return a usage document, probing vendors when the cache is missing or stale.

    refresh=True always probes. A cache hit emits no meter event. Timeout and
    per-harness failures stay inside the probe_* functions (unknown rows).
    """
    ttl = TTL_MIN_DEFAULT if max_age_min is None else max_age_min
    d = None if refresh else load_cache(ttl, cache_path=cache_path)
    if d is None:
        lanes = probe_codex() + probe_agy() + probe_claude() + probe_grok()
        now = time.time()
        d = {"probed_at": now, "probed_at_iso": datetime.fromtimestamp(now, timezone.utc).isoformat(),
             "rollover_min": ROLLOVER_MIN, "lanes": lanes}
        write_cache(d, cache_path=cache_path)
        d = _fill_document(d)
        d["from_cache"] = False
    else:
        d = _fill_document(d)
        d["from_cache"] = True
    return d

def acquire(refresh=False, max_age_min=None, timeout=180):
    """Shared bounded acquisition for callers; cached-only viewers use load_cached.

    Keep a process boundary around vendor probes: their stream reads may block
    despite per-vendor timeouts. The CLI process owns probe/cache/event writes.
    A timeout or failed probe returns a valid, fresh cached document, or {}.
    """
    command = [sys.executable, os.path.abspath(__file__)]
    if refresh:
        command.append("--refresh")
    if max_age_min is not None:
        command.extend(["--max-age-min", str(max_age_min)])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            doc = json.loads(result.stdout)
            if isinstance(doc, dict) and observations(doc) is not None:
                return _fill_document(doc)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    cached = load_cache(TTL_MIN_DEFAULT if max_age_min is None else max_age_min)
    return _fill_document(cached) if cached is not None else {}


def main():
    args = sys.argv[1:]
    refresh = "--refresh" in args; pretty = "--pretty" in args
    ttl = TTL_MIN_DEFAULT
    if "--max-age-min" in args: ttl = float(args[args.index("--max-age-min") + 1])
    d = probe(refresh=refresh, max_age_min=ttl)
    if pretty:
        age = int((time.time() - d["probed_at"]) / 60)
        print(f"# usage (cache age {age} min, from_cache={d['from_cache']})")
        for L in d["lanes"]:
            def f(x): return "  ?" if x is None else f"{int(round(x*100)):3d}%"
            rb = L.get("reset_binding")
            rb = datetime.fromtimestamp(rb).strftime("%b %d %H:%M") if rb else "-"
            pace = "   ?" if L.get('pace') is None else f"{L['pace']:4.2f}"
            print(f"{L['lane']:<18} pace={pace}  r={f(L['r'])}  5h={f(L['remaining_5h'])}  wk={f(L['remaining_weekly'])}  "
                  f"binding={L['binding'] or '-':<6} reset={rb:<12} {L['status']}"
                  f"{' ROLLOVER-SOON' if L['rollover_soon'] else ''}  {L.get('note') or ''}")
    else:
        print(json.dumps(d, indent=1))

if __name__ == "__main__":
    main()
