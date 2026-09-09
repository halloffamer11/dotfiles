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
  ledger.jsonl  machine events from dispatch.sh / usage.py, for the monitor TUI.
  runs.jsonl    what the LEAD concluded after verifying a dispatch — the work
                label and whether the definition of done was met. Only the lead
                knows this, so only the lead writes it.
Run ledger path: $DELEGATE_RUNS else ~/.cache/delegate/runs.jsonl.
"""
import argparse, json, os, subprocess, sys, time
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

try:
    from catalog import load_catalog, CatalogError
except ImportError:
    from .catalog import load_catalog, CatalogError

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.environ.get("DELEGATE_RUNS") or os.path.expanduser("~/.cache/delegate/runs.jsonl")
CACHE = os.environ.get("DELEGATE_CACHE") or os.path.expanduser("~/.cache/delegate/usage.json")
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


def usage_doc(refresh=False, max_age_min=None):
    cmd = [sys.executable, os.path.join(HERE, "usage.py")]
    if refresh:
        cmd.append("--refresh")
    if max_age_min is not None:
        cmd += ["--max-age-min", str(max_age_min)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    try:
        return json.loads(p.stdout)
    except Exception:
        with open(CACHE) as f:      # a probe that failed is not a reason to print nothing
            return json.load(f)


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
    doc = usage_doc(a.refresh, a.max_age_min)
    by_meter = models_by_meter(catalog)
    lanes = sorted(doc["lanes"], key=lambda L: (L.get("remaining_weekly") is None,
                                                -(L.get("remaining_weekly") or 0)))
    skipped = [L["lane"] for L in lanes if ignored(L, by_meter)]
    shown = [L for L in lanes
             if (a.all or not ignored(L, by_meter))
             and (not a.eligible or L.get("status") == "ok")]
    rows = [[L["lane"], model_cell(L, by_meter), pct(L.get("remaining_weekly")),
             pct(L.get("remaining_5h")), when(L.get("reset_weekly")), when(L.get("reset_5h"))]
            for L in shown]
    age = int((time.time() - doc["probed_at"]) / 60)
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
    print(f"\nProbed {age} min ago. A meter under 10% remaining is skipped by rank.py.")


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
    log.add_argument("--thread", default=None, help="thread_id, once dispatch.sh emits one")
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

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
