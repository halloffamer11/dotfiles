#!/usr/bin/env python3
"""report.py — the two tables the session prints after delegating.

Deterministic rendering, so every report has the same shape:

  report.py limits            Markdown table of every meter: weekly and 5h
                              remaining, the model each meter runs, both resets.
                              Then a plan-consumption table for this cycle.
  report.py log ...           append one adjudicated dispatch to the run ledger.
  report.py log --run DIR     same, plus token cost from DIR/dispatch.json.
  report.py runs [--last N]   Markdown table of recent dispatches + the roll-up.
  report.py cost DIR          token-cost breakdown for one run.

Two ledgers exist and they are not the same file:
  ledger.jsonl  machine events from delegate.py / usage.py, for the monitor TUI.
  runs.jsonl    what the LEAD concluded after verifying a dispatch — the work
                label and whether the definition of done was met. Only the lead
                knows this, so only the lead writes it.
Run ledger path: $DELEGATE_RUNS else ~/.cache/delegate/runs.jsonl.
"""
import argparse, json, os, re, shutil, sys, time
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

try:
    from catalog import load_catalog, CatalogError, HARNESSES, meters_enabled
except ImportError:
    from .catalog import load_catalog, CatalogError, HARNESSES, meters_enabled

try:
    from rank import rank
except ImportError:
    from .rank import rank

try:
    import usage
except ImportError:
    from . import usage

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.environ.get("DELEGATE_RUNS") or os.path.expanduser("~/.cache/delegate/runs.jsonl")
CACHE = usage.get_cache_path()
# Flag file: while it exists, `statusline` prints no rows.
SWITCH = os.environ.get("DELEGATE_STATUSLINE_SWITCH") or os.path.expanduser("~/.cache/delegate/statusline.off")
VERDICTS = ("clean", "findings", "partial", "failed")
DAYS_PER_MONTH = 30.4375
WEEK_DAYS = 7
INPUT_KEYS = ("input_tokens", "inputTokens", "prompt_tokens", "promptTokens")
OUTPUT_KEYS = ("output_tokens", "outputTokens", "completion_tokens", "completionTokens")
CACHE_READ_KEYS = ("cache_read_input_tokens", "cachedInputTokens", "cached_tokens", "cache_read_tokens")
CACHE_WRITE_KEYS = ("cache_creation_input_tokens", "cacheCreationInputTokens")


# ---------------------------------------------------------------- shared
def md_table(headers, rows):
    """Left-aligned Markdown table, columns padded to the widest cell."""
    w = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h))
         for i, h in enumerate(headers)]
    out = ["| " + " | ".join(str(h).ljust(w[i]) for i, h in enumerate(headers)) + " |",
           "|" + "|".join("-" * (w[i] + 2) for i in range(len(headers))) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).ljust(w[i]) for i, c in enumerate(r)) + " |")
    return "\n".join(out)


def pct(x):
    return "—" if x is None else f"{int(round(x * 100))}%"


def when(epoch, now=None):
    """'Sep 8 14:59 (5d)' — absolute plus how long is left to spend the window."""
    if not epoch:
        return "—"
    now = now or time.time()
    left = epoch - now
    if left < 0:
        span = "due"
    elif left < 3600:
        span = f"{max(1, round(left / 60))}m"
    elif round(left / 3600) < 24:
        span = f"{round(left / 3600)}h"     # round, not floor: 2.0 days must not read 1d
    else:
        span = f"{round(left / 86400)}d"
    return f"{datetime.fromtimestamp(epoch).strftime('%b %-d %H:%M')} ({span})"


def secs_cell(secs):
    """Plain seconds, always. One unit keeps the column scannable; the roll-up
    line under the table carries the minutes."""
    return f"{int(secs)}s"


def money(amount):
    """Format dollars as $12.34, rounding half-up to the cent."""
    q = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${q}"


def plain_num(x):
    """Trim trailing zeros so 0.445 and 0.025 stay exact in the cost table."""
    return f"{x:.6f}".rstrip("0").rstrip(".")


def load_catalog_or_die(config_dir):
    try:
        return load_catalog(config_dir=config_dir)
    except CatalogError as e:
        sys.stderr.write(f"report: {e}\n")
        sys.exit(1)


# ---------------------------------------------------------------- limits
def models_by_meter(catalog):
    """meter name -> the model slugs catalog lanes actually dispatch on it."""
    out = {}
    for lane in catalog["lanes"].values():
        out.setdefault(lane["meter"], []).append(lane["model"])
    return out


def model_cell(lane_row, by_meter):
    """What runs on this meter. Claude meters are this session, not a lane."""
    slugs = by_meter.get(lane_row["lane"])
    if slugs:
        return ", ".join(sorted(set(slugs)))
    m = lane_row.get("meter") or "general"
    return "this session (all models)" if m == "general" else f"this session ({m})"


def ignored(lane_row, by_meter):
    """A meter no lane can spend, on a harness that is not this session, is ignored
    on purpose — agy's Claude/GPT group after Opus was dropped. Derived, not listed:
    add a lane on that meter to the catalog and it returns to the table."""
    return not by_meter.get(lane_row["lane"]) and lane_row["harness"] != "claude"


def usage_doc(refresh=False, max_age_min=None, routing=None):
    if refresh:
        return usage.acquire(refresh=True, max_age_min=max_age_min, timeout=180)
    if routing is not None and not meters_enabled(routing):
        return usage.load_cached()
    return usage.acquire(refresh=refresh, max_age_min=max_age_min, timeout=180)


def month_cell(price_month):
    if isinstance(price_month, int) or price_month == int(price_month):
        return f"${int(price_month)}"
    return f"${price_month}"


def plan_row(lane_row, meters):
    """One Plan consumption row. Unknown meters dash the last two columns."""
    name = lane_row["lane"]
    meter = meters.get(name)
    used = None if lane_row.get("remaining_weekly") is None else 1 - lane_row["remaining_weekly"]
    if not meter:
        return [name, "—", "—", "—", "—"]
    if used is None:
        return [name, meter["plan"], month_cell(meter["price_month"]), "—", "—"]
    dollars = meter["price_month"] * (WEEK_DAYS / DAYS_PER_MONTH) * used
    return [name, meter["plan"], month_cell(meter["price_month"]), pct(used), money(dollars)]


def cmd_limits(a):
    catalog = load_catalog_or_die(a.config_dir)
    routing = catalog.get("routing", {})
    metering = meters_enabled(routing)
    doc = usage_doc(a.refresh, a.max_age_min, routing=routing)
    gate = routing.get("gate", 0.1)
    obs_map = usage.observations(doc) or {}
    by_meter = models_by_meter(catalog)
    lanes = sorted((dict(L, lane=name, harness=L.get("harness", name.split("-", 1)[0]))
                    for name, L in obs_map.items()),
                   key=lambda L: (L.get("remaining_weekly") is None,
                                  -(L.get("remaining_weekly") or 0)))
    skipped = [L["lane"] for L in lanes if ignored(L, by_meter)]
    shown = [L for L in lanes
             if (a.all or not ignored(L, by_meter))
             and (not a.eligible or not metering or usage.eligible(obs_map.get(L["lane"]), gate))]
    rows = [[L["lane"], model_cell(L, by_meter), pct(L.get("remaining_weekly")),
             pct(L.get("remaining_5h")), when(L.get("reset_weekly")), when(L.get("reset_5h"))]
            for L in shown]
    stamp = doc.get("probed_at")
    age = int((time.time() - stamp) / 60) if isinstance(stamp, (int, float)) else None
    print("**Current limits:**\n")
    print(md_table(["Lane", "Model", "Weekly", "5h", "Weekly reset", "5h reset"], rows))
    plan_rows = []
    seen = set()
    for L in lanes:
        name = L["lane"]
        if name in seen:
            continue
        seen.add(name)
        if name in catalog["meters"]:
            plan_rows.append(plan_row(L, catalog["meters"]))
        elif a.all or not ignored(L, by_meter):
            plan_rows.append(plan_row(L, catalog["meters"]))
    if plan_rows:
        print("\n**Plan consumption this cycle:**\n")
        print(md_table(
            ["Meter", "Plan", "$/month", "Weekly used", "Plan $ used this cycle"],
            plan_rows,
        ))
        print("\nPlan $ used this cycle is the weekly slice of the monthly fee times the share used.")
    unknown = [L["lane"] for L in shown if L.get("remaining_weekly") is not None
               and not L.get("reset_weekly")]
    if unknown:
        print(f"\nWeekly reset unread for: {', '.join(unknown)}.")
    if skipped and not a.all:
        print(f"\nIgnored, no lane spends them: {', '.join(skipped)}.")
    gate_pct = f"{int(round(gate * 100))}%"
    age_label = f"{age} min ago" if age is not None else "at an unknown time"
    if metering:
        print(f"\nProbed {age_label}. A meter under {gate_pct} remaining is skipped by rank.py.")
    else:
        print(f"\nCached {age_label}. Metering is off; ranking does not skip by Gate.")


# ---------------------------------------------------------------- cost
def _first_present(obj, keys):
    for k in keys:
        if k in obj and obj[k] is not None:
            return obj[k]
    return None


def compute_cost(usage, lane_name, catalog):
    """Token dollars for one dispatch. Unmeasured when the relay sent no counts."""
    if not isinstance(usage, dict):
        return {"measured": False, "reason": "relay reported no token usage"}
    input_raw = _first_present(usage, INPUT_KEYS)
    output_raw = _first_present(usage, OUTPUT_KEYS)
    if input_raw is None and output_raw is None:
        return {"measured": False, "reason": "relay reported no token usage"}
    lane = catalog["lanes"].get(lane_name)
    if not lane:
        return {"measured": False, "reason": "lane not in catalog"}
    price = lane["price"]
    tokens = {
        "in": 0 if input_raw is None else input_raw,
        "out": 0 if output_raw is None else output_raw,
        "cache_read": _first_present(usage, CACHE_READ_KEYS) or 0,
        "cache_write": _first_present(usage, CACHE_WRITE_KEYS) or 0,
    }
    usd = {}
    unpublished = []
    for key, n in tokens.items():
        p = price.get(key)
        if p is None:
            usd[key] = 0
            unpublished.append(key)
        else:
            usd[key] = n / 1_000_000 * p
    note = ""
    if unpublished:
        note = "unpublished price: " + ", ".join(unpublished)
    return {
        "measured": True,
        "input_tokens": tokens["in"],
        "output_tokens": tokens["out"],
        "cache_read_tokens": tokens["cache_read"],
        "cache_write_tokens": tokens["cache_write"],
        "usd_in": usd["in"],
        "usd_out": usd["out"],
        "usd_cache_read": usd["cache_read"],
        "usd_cache_write": usd["cache_write"],
        "usd_total": usd["in"] + usd["out"] + usd["cache_read"] + usd["cache_write"],
        "note": note,
    }


def read_dispatch(run_dir):
    path = os.path.join(os.path.expanduser(run_dir), "dispatch.json")
    try:
        with open(path) as f:
            doc = json.load(f)
    except FileNotFoundError:
        sys.exit(f"report: {path}: file is missing")
    except json.JSONDecodeError as e:
        sys.exit(f"report: {path}: JSON syntax error: {e.msg}")
    except OSError as e:
        sys.exit(f"report: {path}: {e}")
    if not isinstance(doc, dict):
        sys.exit(f"report: {path}: dispatch.json must be an object")
    return doc


def price_cell(p):
    return "—" if p is None else plain_num(p)


def cmd_cost(a):
    catalog = load_catalog_or_die(a.config_dir)
    dispatch = read_dispatch(a.run_dir)
    lane = dispatch.get("lane")
    cost = compute_cost(dispatch.get("usage"), lane, catalog)
    if not cost.get("measured"):
        print(f"unmeasured: {cost.get('reason', '')}")
        return
    price = catalog["lanes"].get(lane, {}).get("price") or {}
    rows = [
        ["input", cost["input_tokens"], price_cell(price.get("in")), plain_num(cost["usd_in"])],
        ["output", cost["output_tokens"], price_cell(price.get("out")), plain_num(cost["usd_out"])],
        ["cache_read", cost["cache_read_tokens"], price_cell(price.get("cache_read")),
         plain_num(cost["usd_cache_read"])],
        ["cache_write", cost["cache_write_tokens"], price_cell(price.get("cache_write")),
         plain_num(cost["usd_cache_write"])],
        ["total", "", "", plain_num(cost["usd_total"])],
    ]
    print(md_table(["Component", "Tokens", "$/M", "$"], rows))
    if cost.get("note"):
        print(f"\n{cost['note']}")


# ---------------------------------------------------------------- runs
def append_run(rec):
    os.makedirs(os.path.dirname(RUNS), exist_ok=True)
    with open(RUNS, "a") as f:
        f.write(json.dumps(rec) + "\n")


def cmd_log(a):
    if a.verdict not in VERDICTS:
        sys.exit(f"verdict must be one of {', '.join(VERDICTS)}")
    dispatch = read_dispatch(a.run_dir) if a.run_dir else None
    lane = a.lane or (dispatch or {}).get("lane")
    if not lane:
        sys.exit("report: --lane is required unless --run names a dispatch.json with lane")
    if a.secs is not None:
        secs = int(a.secs)
    else:
        ds = None if dispatch is None else dispatch.get("secs")
        if ds is None:
            sys.exit("report: --secs is required unless --run names a dispatch.json with secs")
        secs = int(ds)
    status = a.status if a.status is not None else ((dispatch or {}).get("status") or "done")
    thread = a.thread if a.thread is not None else (None if dispatch is None else dispatch.get("thread_id"))
    rec = {"v": 1, "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "work": a.work, "lane": lane, "class": a.klass, "secs": secs,
           "rc": a.rc, "status": status, "verdict": a.verdict, "outcome": a.outcome,
           "thread_id": thread, "batch": a.batch}
    if a.run_dir:
        catalog = load_catalog_or_die(a.config_dir)
        rec["cost"] = compute_cost((dispatch or {}).get("usage"), lane, catalog)
    append_run(rec)
    extra = ""
    if "cost" in rec:
        extra = f" {money(rec['cost']['usd_total'])}" if rec["cost"].get("measured") else " unmeasured"
    print(f"logged: {a.work} → {lane} {secs_cell(secs)} {a.verdict}{extra}")


def read_runs():
    try:
        with open(RUNS) as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def cost_cell(rec):
    c = rec.get("cost")
    if not c:
        return "—"
    if not c.get("measured"):
        return "unmeasured"
    total = c.get("usd_total") or 0
    if 0 < total < 0.01:
        return "<$0.01"
    return money(total)


def cmd_runs(a):
    recs = read_runs()
    if a.batch:
        recs = [r for r in recs if r.get("batch") == a.batch]
    recs = recs[-a.last:] if a.last else recs
    if not recs:
        print("No runs logged yet.")
        return
    rows = [[r["work"], r["lane"], secs_cell(r["secs"]), cost_cell(r),
             r.get("outcome") or r["verdict"]] for r in recs]
    total = sum(r["secs"] for r in recs)
    bad = [r for r in recs if r["verdict"] in ("partial", "failed") or r.get("rc")]
    head = (f"{len(recs)} dispatches, all rc=0, zero failed lanes."
            if not bad else
            f"{len(recs)} dispatches, {len(bad)} needing a second pass.")
    print(head + "\n")
    print(md_table(["Work", "Lane", "Wall time", "Cost", "Outcome"], rows))
    line = (f"\n~{round(total / 60)} minutes of lane wall-time"
            f" across {len({r['lane'] for r in recs})} lanes, mostly in parallel.")
    costed = [r for r in recs if r.get("cost")]
    if costed:
        measured = [r for r in costed if r["cost"].get("measured")]
        n_unm = sum(1 for r in costed if not r["cost"].get("measured"))
        usd = sum(r["cost"].get("usd_total") or 0 for r in measured)
        line += f"; {money(usd)} measured across {len(measured)} runs, {n_unm} unmeasured"
    print(line)


# ---------------------------------------------------------------- statusline
ANSI = re.compile(r"\033\[[0-9;]*m")
TIER_GLYPH = {1: "①", 2: "②", 3: "③", 4: "④"}


def vis(s):
    return len(ANSI.sub("", s))


def pad(s, w):
    return s + " " * max(0, w - vis(s))


def rpad(s, w):
    return " " * max(0, w - vis(s)) + s


def get_colors(no_color):
    if no_color:
        return {
            "R": "", "BOLD": "", "DIM": "",
            "GRN": "", "CYAN": "", "YEL": "", "MAG": "",
            "RED": "", "MUTE": "", "FG": "",
            "TIER_COL": {1: "", 2: "", 3: "", 4: ""}
        }
    def rgb(h):
        return f"\033[38;2;{int(h[0:2], 16)};{int(h[2:4], 16)};{int(h[4:6], 16)}m"
    grn = rgb("78bd74")
    cyan = rgb("1fb5bc")
    yel = rgb("c68f32")
    mag = rgb("be80ca")
    red = rgb("d76563")
    mute = rgb("8d8d89")
    fg = rgb("e7e7e7")
    return {
        "R": "\033[0m", "BOLD": "\033[1m", "DIM": "\033[2m",
        "GRN": grn, "CYAN": cyan, "YEL": yel, "MAG": mag,
        "RED": red, "MUTE": mute, "FG": fg,
        "TIER_COL": {1: grn, 2: cyan, 3: yel, 4: mag}
    }


def dur_short(t, now):
    """Coarse: largest whole unit, floored — 4d, 2h, 46m."""
    if t is None:
        return ""
    s = max(0, int(t - now))
    return f"{s // 86400}d" if s >= 86400 else f"{s // 3600}h" if s >= 3600 else f"{s // 60}m"


def bar(u, n=5, gated=False, c=None):
    """Remaining as a fuel gauge: full cells from the left."""
    if u is None:
        return f"{c['MUTE']}{'·' * n}{c['R']}"
    blocks = " ▏▎▍▌▋▊▉█"
    full = min(n, int(u * n))
    eighth = round((u * n - full) * 8) if full < n else 0
    part = blocks[eighth] if eighth else ""
    col = c["RED"] if gated else c["FG"]
    return f"{col}{'█' * full}{part}{c['R']}{c['MUTE']}{'░' * (n - full - len(part))}{c['R']}"


def pct_cell(u, gated=False, c=None):
    if u is None:
        return f"{c['MUTE']}—{c['R']}"
    col = c["RED"] if gated else c["FG"]
    return f"{col}{round(u * 100)}%{c['R']}"


def num(u, reset, now, gated=False, c=None):
    """'58%·2h', or a lone dash when the meter has no such window."""
    if u is None:
        return rpad(pct_cell(u, gated, c), 4)
    d = dur_short(reset, now)
    return f"{rpad(pct_cell(u, gated, c), 4)}{c['DIM']}·{d}{c['R']}"


def gauge(u, reset, now, gated=False, c=None):
    return f"{bar(u, gated=gated, c=c)} {num(u, reset, now, gated=gated, c=c)}"


def get_meter_label(m_key, meter_def, all_meters):
    harness = meter_def.get("harness") or m_key
    harness_meters = [k for k, m in all_meters.items() if m.get("harness") == harness]
    if len(harness_meters) <= 1:
        return harness
    suffix = m_key.split("-", 1)[1] if "-" in m_key else m_key
    if suffix == "general":
        return harness
    return suffix


def format_label(lbl, won_tiers, c):
    won = sorted(won_tiers)
    col = c["TIER_COL"][won[0]] if won else c["MUTE"]
    return f"{col}{c['BOLD']}{lbl}{c['R']}"


def format_badge(won_tiers, c):
    # Claude Code trims leading whitespace off every status line row, so an
    # unbadged row keeps its column with a dim placeholder, never with spaces.
    if not won_tiers:
        return f"{c['MUTE']}·{c['R']}"
    return "".join(f"{c['TIER_COL'][t]}{TIER_GLYPH[t]}{c['R']}" for t in sorted(won_tiers))


def statusline_switch(state):
    """on / off / toggle / status for the rows; the switch is a flag file."""
    path = SWITCH
    if state == "status":
        print("off" if os.path.exists(path) else "on")
        return
    if state == "toggle":
        state = "on" if os.path.exists(path) else "off"
    if state == "off":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("delegate status line rows are off; remove this file or run "
                    "`report.py statusline on` to show them\n")
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    print(f"delegate rows {state}")


def running_glyphs(running_tiers, c):
    return "".join(
        f"{c['TIER_COL'][t]}{TIER_GLYPH[t] * running_tiers[t]}{c['R']}"
        for t in sorted(running_tiers)
        if running_tiers[t] > 0
    )


def cmd_statusline(a):
    if a.state:
        statusline_switch(a.state)
        return
    if os.path.exists(SWITCH):
        return
    no_color = a.no_color or bool(os.environ.get("NO_COLOR"))
    c = get_colors(no_color)
    catalog = load_catalog_or_die(a.config_dir)

    cache_path = usage.get_cache_path()
    if not os.path.exists(cache_path):
        return
    usage_doc = usage.load_cached(cache_path)
    obs_map = usage.observations(usage_doc)
    if obs_map is None:
        return
    if not isinstance(usage_doc, dict) or not isinstance(usage_doc.get("lanes"), list):
        return

    now = time.time()
    present = {h for h in HARNESSES if shutil.which(h)}
    routing = catalog.get("routing", {})
    classes = routing.get("classes", {})
    gate_threshold = routing.get("gate", 0.10)
    metering = meters_enabled(routing)

    won_by_meter = {}
    for cls in classes:
        try:
            rows = rank(cls, catalog, usage_doc, present)
        except Exception:
            continue
        if rows and rows[0].get("pick"):
            picked = rows[0]
            m_name = picked.get("meter")
            tier = picked.get("tier")
            if m_name and tier is not None:
                won_by_meter.setdefault(m_name, set()).add(tier)

    ledger_path = os.environ.get("DELEGATE_LEDGER") or os.path.expanduser("~/.cache/delegate/ledger.jsonl")
    running_by_lane = Counter()
    if os.path.exists(ledger_path):
        try:
            starts = {}
            with open(ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    k = e.get("kind")
                    tid = e.get("thread_id")
                    if k == "dispatch.start" and tid:
                        starts[tid] = e
                    elif k == "dispatch.finish" and tid:
                        starts.pop(tid, None)
            for e in starts.values():
                ts_str = e.get("ts")
                timeout_s = e.get("timeout_s") or 0
                if ts_str:
                    try:
                        t = datetime.fromisoformat(ts_str).timestamp()
                    except Exception:
                        continue
                    if now <= t + timeout_s:
                        lane_name = e.get("lane")
                        if lane_name:
                            running_by_lane[lane_name] += 1
        except Exception:
            return

    by_meter = {L["lane"]: L for L in usage_doc.get("lanes", []) if isinstance(L, dict) and "lane" in L}
    all_meters = catalog.get("meters", {})
    catalog_order = list(all_meters.keys())

    def sort_key(m_key):
        won = won_by_meter.get(m_key)
        has_badge = bool(won)
        min_t = min(won) if has_badge else 99
        cat_idx = catalog_order.index(m_key) if m_key in catalog_order else 999
        return (0 if has_badge else 1, min_t, cat_idx)

    sorted_meters = sorted(catalog_order, key=sort_key)

    out_lines = []
    if not metering:
        out_lines.append(f"{c['DIM']}meters off{c['R']}")
    for m_key in sorted_meters:
        m_def = all_meters.get(m_key, {})
        lbl = get_meter_label(m_key, m_def, all_meters)
        u_row = by_meter.get(m_key, {})
        rem5 = u_row.get("remaining_5h")
        reset5 = u_row.get("reset_5h")
        remw = u_row.get("remaining_weekly")
        resetw = u_row.get("reset_weekly")
        model_remw = u_row.get("remaining_weekly_model")
        shares5 = (model_remw is not None) or (m_key == "claude-fable")
        if model_remw is not None:
            remw = model_remw

        is_gated = metering and not usage.eligible(obs_map.get(m_key, u_row), gate_threshold)

        won_tiers = won_by_meter.get(m_key, set())
        badge_str = format_badge(won_tiers, c)
        label_str = format_label(lbl, won_tiers, c)

        if shares5:
            five_str = " " * 15
        else:
            five_str = f"{c['DIM']}5h{c['R']} {gauge(rem5, reset5, now, gated=False, c=c)}"

        gate_char = f"{c['RED']}{c['BOLD']}✗{c['R']}" if is_gated else ""
        wk_str = f"{c['DIM']}wk{c['R']} {gauge(remw, resetw, now, gated=is_gated, c=c)}{gate_char}"

        line = f"{pad(badge_str, 3)}{pad(label_str, 7)}{pad(five_str, 17)}{pad(wk_str, 17)}"

        if not a.no_running:
            running_tiers = Counter()
            for lane_name, count in running_by_lane.items():
                lane_def = catalog.get("lanes", {}).get(lane_name)
                if lane_def and lane_def.get("meter") == m_key:
                    running_tiers[lane_def["tier"]] += count
            glyphs = running_glyphs(running_tiers, c)
            if glyphs:
                line += " " + glyphs

        out_lines.append(line.rstrip())

    for l in out_lines:
        print(l)


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    cfg = argparse.ArgumentParser(add_help=False)
    cfg.add_argument("--config-dir", default=None,
                     help="catalog directory (default ~/.config/delegate)")

    lim = sub.add_parser("limits", parents=[cfg], help="the Current limits table")
    lim.add_argument("--refresh", action="store_true", help="force a re-probe")
    lim.add_argument("--max-age-min", type=float, help="cache TTL override")
    lim.add_argument("--eligible", action="store_true", help="drop meters rank.py would skip")
    lim.add_argument("--all", action="store_true", help="include meters no lane can spend")
    lim.set_defaults(fn=cmd_limits)

    log = sub.add_parser("log", parents=[cfg], help="append one adjudicated dispatch")
    log.add_argument("--work", required=True, help="what the child was asked to do, 2-4 words")
    log.add_argument("--lane", default=None)
    log.add_argument("--secs", default=None, type=int, help="wall time from the dispatch line")
    log.add_argument("--verdict", required=True, choices=VERDICTS, help="the LEAD's adjudication")
    log.add_argument("--outcome", default="", help="one phrase, e.g. '4 findings, all real'")
    log.add_argument("--class", dest="klass", default=None)
    log.add_argument("--rc", type=int, default=0)
    log.add_argument("--status", default=None, help="status field of the out file")
    log.add_argument("--thread", default=None, help="thread_id from the delegate-metrics: line")
    log.add_argument("--batch", default=None, help="tag grouping one fan-out")
    log.add_argument("--run", dest="run_dir", default=None,
                     help="run directory; read lane, usage, secs, status, thread_id from dispatch.json")
    log.set_defaults(fn=cmd_log)

    run = sub.add_parser("runs", parents=[cfg], help="the dispatch table")
    run.add_argument("--last", type=int, default=0)
    run.add_argument("--batch", default=None)
    run.set_defaults(fn=cmd_runs)

    cost = sub.add_parser("cost", parents=[cfg], help="token cost for one run")
    cost.add_argument("run_dir", help="run directory with dispatch.json")
    cost.set_defaults(fn=cmd_cost)

    sl = sub.add_parser("statusline", parents=[cfg], help="Claude Code statusline meter rows")
    sl.add_argument("--no-color", action="store_true", help="strip ANSI color escapes")
    sl.add_argument("--no-running", action="store_true", help="suppress the running agents column")
    sl.add_argument("state", nargs="?", choices=["on", "off", "toggle", "status"],
                    help="switch the rows instead of printing them (flag file ~/.cache/delegate/statusline.off)")
    sl.set_defaults(fn=cmd_statusline)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
