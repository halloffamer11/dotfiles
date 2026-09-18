#!/usr/bin/env python3
"""PROTOTYPE: the instrument-panel layout for the delegate dashboard.

Throwaway.  One Lane to a row on a fixed character grid; colour carries state
and never identity; Tier identity is demoted to a one-cell rail so no Tier hue
competes with a state hue on the same row.  The boldness is spent in two
places only: the Meter strip and the Remaining bars, because Remaining and Pace
belong to the Meter and are what the Gate acts on.

The layout is the "instrument panel" proposal in
``.scratch/delegate-dashboard-plugin/_work/tui-review/review-opus-high.md``.
The Tier-leader strip is taken from the second proposal in the same folder,
``review-grok46-high.md``.

Standard library only.
"""

from __future__ import annotations

import os
import unicodedata


NAME = "panel"

# No capture proves the pane font, so the patched glyphs stay behind a switch.
NERD = os.environ.get("DELEGATE_DASHBOARD_NERD") == "1"
LIGHT = os.environ.get("DELEGATE_DASHBOARD_THEME") == "light"

RESET = "\033[0m"

# Role, not identity.  A hue means a state of the Lane, never which Tier it is in.
DARK = {
    "text": "#E7E7E7",
    "dim": "#8D8D89",
    "selbg": "#2A3140",
    "pick": "#F2C14E",
    "ok": "#7FBF6B",
    "watch": "#D9A441",
    "veto": "#D97070",
    "unknown": "#8A8FA0",
}
LIGHT_ROLES = {
    "text": "#1C1C1C",
    "dim": "#6E6E6A",
    "selbg": "#DCE6F5",
    "pick": "#8A5A00",
    "ok": "#2F7D2B",
    "watch": "#8A5D00",
    "veto": "#A32F2F",
    "unknown": "#6B6F80",
}
RAIL_DARK = {1: "#5FB37A", 2: "#2FA8B8", 3: "#C08A3E", 4: "#A97BD1"}
RAIL_LIGHT = {1: "#2E7D50", 2: "#17707C", 3: "#8A5D14", 4: "#6E4699"}

ROLES = LIGHT_ROLES if LIGHT else DARK
RAIL_COLORS = RAIL_LIGHT if LIGHT else RAIL_DARK

# Nerd Font code point, then the plain-Unicode fallback that holds the columns
# without a patched font.  The code points come from the proposal and are not
# verified against an installed font map.
GLYPHS = {
    "pick": ("", "★"),
    "ok": ("", "✓"),
    "veto": ("", "⊘"),
    "unknown": ("", "?"),
    "steal": ("", "»"),
    "project": ("", "▪"),
    "cursor": ("", "›"),
    "open": ("", "▾"),
    "folded": ("", "▸"),
}
RAIL = "▌"
LEADER = "◆"
CARRIED = "·"
BAR_FULL = "█"
BAR_EMPTY = "░"
BAR_PARTIAL = " ▏▎▍▌▋▊▉"
BAR_UNKNOWN = "╌"
SPARK = "▁▂▃▄▅▆▇█"

# Fixed grid.  One space between every field; `note` takes the remainder.
PLAN = (
    ("rail", 1),
    ("cursor", 1),
    ("mark", 1),
    ("ord", 3),
    ("lane", 19),
    ("model", 23),
    ("meter", 14),
    ("bar", 6),
    ("rem", 4),
    ("pace", 6),
    ("ok", 1),
    ("note", 0),
)
ALIGN = {"ord": ">", "rem": ">", "pace": ">"}
LABELS = {"ord": "Ord", "lane": "Lane", "model": "Model", "meter": "Meter",
          "rem": "Rem", "pace": "Pace", "note": "Note"}

HELP = (
    ("j / k   ↑ / ↓", "select the Lane above or below"),
    ("J / K   ⇧↑ / ⇧↓", "move the Lane inside its Tier"),
    ("1 2 3 4", "select the first Lane of that Tier"),
    ("[  ]", "select the first Lane of the previous or next Tier"),
    ("e", "show only eligible Lanes"),
    ("z", "fold the Tier under the cursor"),
    ("Z", "fold every Tier but this one"),
    ("g / m", "edit the project Gate or Margin"),
    ("r", "reload the catalog and the Meter cache"),
    ("v", "switch to the next layout"),
    ("?", "close this help"),
    ("q", "close the dashboard"),
)


def glyph(key):
    return GLYPHS[key][0] if NERD else GLYPHS[key][1]


# --- terminal cells ---------------------------------------------------------


def cells(text):
    """Width of `text` in terminal cells.  Ambiguous-width glyphs count as one."""
    total = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        total += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return total


def fit(text, width):
    """Clip to `width` cells, marking a clipped string with an ellipsis."""
    if width <= 0:
        return ""
    if cells(text) <= width:
        return text
    if width == 1:
        return "…"
    kept = []
    used = 0
    for char in text:
        step = 0 if unicodedata.combining(char) else (
            2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        )
        if used + step > width - 1:
            break
        kept.append(char)
        used += step
    return "".join(kept) + "…"


def pad(text, width, align="<"):
    text = fit(text, width)
    gap = max(0, width - cells(text))
    return (" " * gap + text) if align == ">" else (text + " " * gap)


def fg(hex_color):
    value = hex_color.removeprefix("#")
    return f"\033[38;2;{int(value[0:2], 16)};{int(value[2:4], 16)};{int(value[4:6], 16)}m"


def bg(hex_color):
    value = hex_color.removeprefix("#")
    return f"\033[48;2;{int(value[0:2], 16)};{int(value[2:4], 16)};{int(value[4:6], 16)}m"


def line(segments, width, *, back=None):
    """Paint (text, role, bold) segments into one line of at most `width` cells."""
    out = []
    used = 0
    for text, role, bold in segments:
        if used >= width:
            break
        piece = fit(text, width - used)
        if not piece:
            continue
        weight = "\033[1m" if bold else ""
        back_code = bg(ROLES[back]) if back else ""
        out.append(weight + back_code + fg(ROLES.get(role, role or "text")) + piece + RESET)
        used += cells(piece)
    if back is not None and used < width:
        out.append(f"{bg(ROLES[back])}{' ' * (width - used)}{RESET}")
    return "".join(out)


# --- reading the state ------------------------------------------------------


def percent(value):
    return "—" if value is None else f"{round(value * 100):g}%"


def pace_text(value):
    return "—" if value is None else f"{value:.2f}×"


def bar(value, width):
    """A Remaining bar in eighths; an unknown Meter draws a dashed rule, not zero."""
    if value is None:
        return BAR_UNKNOWN * width
    filled = max(0.0, min(1.0, value)) * width
    full = int(filled)
    text = BAR_FULL * min(full, width)
    if full < width:
        eighths = int((filled - full) * 8)
        text += BAR_PARTIAL[eighths] if eighths else BAR_EMPTY
        text += BAR_EMPTY * (width - full - 1)
    return text[:width]


def spark(value):
    if value is None:
        return BAR_UNKNOWN
    return SPARK[min(7, max(0, int(max(0.0, min(1.0, value)) * 8)))]


def is_project(source, state):
    return bool(source) and source == state["project"]["policy"]


def lane_state(row, state):
    """Return (role, glyph, note) for one Lane row, from its reason and Meter."""
    reason = row.get("reason") or ""
    gate = state["policy"]["gate"]["display"]
    if reason.startswith("vetoed:"):
        kind = reason[len("vetoed:"):].split(",", 1)[0]
        tail = reason.partition(": ")[2]
        note = f"under Gate {gate}" if kind == "gate" else (tail or reason)
        return "veto", glyph("veto"), note
    if reason == "pick":
        return "pick", glyph("ok"), ""
    if reason.startswith("stolen by pace"):
        return "watch", glyph("steal"), "steal " + (reason.partition(": ")[2] or "")
    if row.get("remaining") is None or reason.startswith("unknown meter"):
        return "unknown", glyph("unknown"), "no Meter reading"
    if row.get("eligible"):
        return "ok", glyph("ok"), ""
    return "veto", glyph("veto"), reason


def meter_role(row, state):
    """Colour Remaining by what the Gate does with it, not by how large it is."""
    remaining = row.get("remaining")
    if remaining is None:
        return "unknown"
    gate = state["policy"]["gate"]["value"] or 0.0
    pace = row.get("pace")
    if remaining < gate:
        return "veto"
    if remaining < 2 * gate or (pace is not None and pace < 0.5):
        return "watch"
    return "ok"


def meters_of(state):
    """Every Meter a carried Lane uses, in the order the Tiers first name it."""
    seen = {}
    for tier in state["tiers"]:
        for row in tier["rows"]:
            seen.setdefault(row["meter"], row["remaining"])
    return list(seen.items())


# --- the grid ---------------------------------------------------------------


def grid(width):
    """Apply the drop ladder and return the columns this width can hold."""
    dropped = set()
    if width < 118:
        dropped.add("model")
    if width < 96:
        dropped.add("meter")
    if width < 78:
        dropped.add("pace")
    if width < 62:
        dropped.add("bar")
    if width < 48:
        dropped.add("note")
    kept = [[key, size] for key, size in PLAN if key not in dropped]

    def consumed(columns):
        return sum(size for _key, size in columns) + max(0, len(columns) - 1)

    if kept and kept[-1][0] == "note":
        note = width - consumed(kept[:-1]) - 1
        if note < 8:
            kept = kept[:-1]
        else:
            kept[-1][1] = note
    # Lane is trimmed last and takes the slack first, because the Lane name is
    # the identity every other dropped column was recoverable from.
    slack = width - consumed(kept)
    for column in kept:
        if column[0] == "lane":
            if slack < 0:
                column[1] = max(8, column[1] + slack)
            elif kept[-1][0] != "note":
                column[1] = min(30, column[1] + slack)
    return [(key, size) for key, size in kept]


def lane_row(row, tier, state, columns, *, selected):
    """One Lane on the fixed grid; every cell starts at the same column always."""
    role, mark_glyph, note = lane_state(row, state)
    rail_hue = RAIL_COLORS[tier["tier"]]
    # The Pick is the one loud mark; a Tier leader that is not the Pick stays quiet.
    if role == "pick":
        mark = glyph("pick")
    elif row["lane"] == tier["leader"]:
        mark = LEADER
    else:
        mark = CARRIED
    order = "—" if row["order"] is None else str(row["order"])
    source = glyph("project") if is_project(row.get("order_source"), state) else " "
    rem_role = meter_role(row, state)
    values = {
        "rail": (RAIL, rail_hue, False),
        "cursor": (glyph("cursor") if selected else " ", "text", True),
        "mark": (mark, "pick" if role == "pick" else "dim", role == "pick"),
        "ord": (f"{order:>2}{source}", "dim", False),
        "lane": (row["lane"], "pick" if role == "pick" else "text", role == "pick"),
        "model": (row["model"], "dim", False),
        "meter": (row["meter"], "dim", False),
        "bar": (None, rem_role, False),
        "rem": (percent(row["remaining"]), rem_role, False),
        "pace": (pace_text(row["pace"]), rem_role, False),
        "ok": (mark_glyph, role, False),
        "note": (note, role, False),
    }
    segments = []
    for index, (key, size) in enumerate(columns):
        if index:
            segments.append((" ", "dim", False))
        text, hue, bold = values[key]
        if key == "bar":
            text = bar(row["remaining"], size)
        segments.append((pad(text, size, ALIGN.get(key, "<")), hue, bold))
    return segments


def tier_row(tier, state, width, *, folded, count, eligible, selected_here):
    leader = tier["leader"] or "none eligible"
    hue = RAIL_COLORS[tier["tier"]]
    mark = glyph("folded") if folded else glyph("open")
    cursor = glyph("cursor") if selected_here else " "
    left = f"{mark}{cursor}Tier {tier['tier']}  "
    lead_mark = LEADER if tier["leader"] else "—"
    head = f"{left}{lead_mark} {leader}"
    tail = f"{count} lane{'' if count == 1 else 's'} · {eligible} elig."
    gap = max(1, width - cells(head) - cells(tail))
    return [
        (left, hue, True),
        (f"{lead_mark} {leader}", "pick" if tier["leader"] else "dim", False),
        (" " * gap, "dim", False),
        (tail, "dim", False),
    ]


# --- chrome -----------------------------------------------------------------


def header_lines(state, width, message):
    gate = state["policy"]["gate"]
    margin = state["policy"]["margin"]
    meters = state["policy"]["meters"]
    off = meters.get("value") is False
    policy_role = "dim" if off else "text"
    # Gate and Margin are the two values this pane edits, so the project name
    # yields its cells to them rather than the other way round.
    policy = [
        (f"Gate {gate['display']}", policy_role, False),
        (glyph("project") if is_project(gate["source"], state) else " ", "dim", False),
        (f"  Margin {margin['display']}", policy_role, False),
        (glyph("project") if is_project(margin["source"], state) else " ", "dim", False),
        (f"  Meters {meters.get('display', 'on')}", "watch" if off else "dim", False),
    ]
    spent = sum(cells(text) for text, _r, _b in policy) + len("delegate") + 4
    identity = [
        ("delegate", "dim", False),
        ("  " + pad(state["project"]["name"], max(6, width - spent)) + "  ", "text", True),
    ] + policy

    strip = [("Meters ", "dim", False)]
    for name, remaining in meters_of(state):
        role = "unknown" if remaining is None else "text"
        strip.append((f" {name} ", "dim", False))
        strip.append((spark(remaining), role, True))
        strip.append((f" {percent(remaining):>4}", role, False))

    leaders = []
    for tier in state["tiers"]:
        leaders.append((f"T{tier['tier']} ", RAIL_COLORS[tier["tier"]], True))
        if tier["leader"]:
            leaders.append((tier["leader"] + "   ", "text", False))
        else:
            leaders.append(("—   ", "dim", False))

    usage = state["usage"]
    if message:
        status = [(message, "watch", False)]
    elif state.get("error"):
        status = [(state["error"], "veto", True)]
    elif state.get("save", {}).get("status") not in (None, "idle") and state["save"].get("detail"):
        saved = state["save"]["status"] == "saved"
        status = [(state["save"]["detail"], "ok" if saved else "veto", not saved)]
    elif off:
        status = [(meters.get("effect") or "", "watch", False)]
    else:
        health = usage["status"]
        status = [
            (f"Meter cache {health}", "dim" if health == "ok" else "veto", False),
            ("   display only   ", "dim", False),
            (usage["path"], "dim", False),
        ]
    return identity, strip, leaders, status


def column_header(columns):
    segments = []
    for index, (key, size) in enumerate(columns):
        if index:
            segments.append((" ", "dim", False))
        segments.append((pad(LABELS.get(key, ""), size, ALIGN.get(key, "<")), "dim", False))
    return segments


# Dropped from the end as the pane narrows; `? help` is the last one to go.
HINTS = (
    "j/k select", "J/K move", "1-4 [ ] Tier",
    "e eligible", "z fold", "g Gate", "m Margin", "r reload",
)


def footer_line(state, editor, index, total, width):
    """The editor lives here, so opening it never moves the list."""
    if width >= 100:
        tail = f"layout: {NAME} (v next)   lane {index} of {total}"
    elif width >= 60:
        tail = f"layout: {NAME} (v next)   {index}/{total}"
    else:
        tail = f"layout: {NAME} (v next)"
    if editor is not None:
        current = state["policy"][editor.field]
        source = "project" if is_project(current["source"], state) else "global"
        mark = glyph("project") if source == "project" else " "
        head = (
            f"{editor.field.title()}  {current['display']}{mark} {source} → "
            f"[ {editor.text}_ ]%   ↵ save   esc cancel"
        )
    else:
        room = width - cells(tail) - 3
        hints = list(HINTS)
        head = "  ".join(hints + ["? help"])
        while hints and cells(head) > room:
            hints.pop()
            head = "  ".join(hints + ["? help"])
    gap = max(1, width - cells(head) - cells(tail))
    return [
        (head, "text" if editor is not None else "dim", editor is not None),
        (" " * gap, "dim", False),
        (tail, "dim", False),
    ]


# --- body -------------------------------------------------------------------


def build_body(state, view, selected_lane):
    """Flatten the Tiers into scrollable items honouring fold and eligible-only."""
    folded = view.setdefault("folded", set())
    eligible_only = view.get("eligible_only", False)
    items = []
    for tier in state["tiers"]:
        rows = tier["rows"]
        shown = [row for row in rows if row["eligible"]] if eligible_only else list(rows)
        here = any(row["lane"] == selected_lane for row in rows)
        is_folded = tier["tier"] in folded
        items.append({
            "kind": "tier",
            "tier": tier,
            "folded": is_folded,
            "count": len(rows),
            "eligible": sum(1 for row in rows if row["eligible"]),
            "selected_here": here and (is_folded or not any(
                row["lane"] == selected_lane for row in shown)),
        })
        if is_folded:
            continue
        if not shown:
            items.append({"kind": "empty", "tier": tier})
            continue
        for row in shown:
            items.append({"kind": "lane", "tier": tier, "row": row})
    return items


def render(state, *, width, height, selected_lane, editor, message, view):
    """Return exactly `height` painted strings, each at most `width` cells."""
    identity, strip, leaders, status = header_lines(state, width, message)
    columns = grid(width)
    lanes = [row["lane"] for tier in state["tiers"] for row in tier["rows"]]
    position = lanes.index(selected_lane) + 1 if selected_lane in lanes else 0
    footer = footer_line(state, editor, position, len(lanes), width)

    chrome = [identity, strip, leaders, status, column_header(columns)]
    body_height = height - len(chrome) - 1
    if body_height < 1:
        # Too short for the panel: keep the identity line and the footer only.
        painted = [line(identity, width), line(footer, width)]
        painted.extend([""] * max(0, height - len(painted)))
        return painted[:height]

    items = build_body(state, view, selected_lane)
    selected_index = next(
        (i for i, item in enumerate(items)
         if item["kind"] == "lane" and item["row"]["lane"] == selected_lane),
        None,
    )
    offset = min(max(0, view.get("offset", 0)), max(0, len(items) - body_height))
    if view.get("last_selected", object()) != selected_lane and selected_index is not None:
        if selected_index < offset:
            offset = selected_index
        elif selected_index >= offset + body_height:
            offset = selected_index - body_height + 1
    view["offset"] = offset
    view["last_selected"] = selected_lane
    view["items"] = len(items)

    body = []
    if view.get("help"):
        body.append(line([("Keys", "text", True)], width))
        for keys, meaning in HELP:
            body.append(line([
                (pad(keys, 17), "pick", False),
                (meaning, "dim", False),
            ], width))
        body = body[:body_height]
    else:
        for item in items[offset : offset + body_height]:
            if item["kind"] == "tier":
                body.append(line(
                    tier_row(item["tier"], state, width, folded=item["folded"],
                             count=item["count"], eligible=item["eligible"],
                             selected_here=item["selected_here"]),
                    width,
                ))
            elif item["kind"] == "empty":
                body.append(line([
                    (RAIL, RAIL_COLORS[item["tier"]["tier"]], False),
                    ("   no Lane to show", "dim", False),
                ], width))
            else:
                selected = item["row"]["lane"] == selected_lane
                body.append(line(
                    lane_row(item["row"], item["tier"], state, columns, selected=selected),
                    width,
                    back="selbg" if selected else None,
                ))
    body.extend([""] * max(0, body_height - len(body)))

    painted = [line(part, width) for part in chrome] + body + [line(footer, width)]
    painted.extend([""] * max(0, height - len(painted)))
    return painted[:height]


def handle_key(key, state, view):
    """Fold, filter, Tier jumps, scroll and help.

    A Lane name returned here asks the host to select that Lane; it is truthy,
    so a host that only tests the result still reads it as "key used".
    """
    tiers = state["tiers"]
    selected = view.get("last_selected")

    def first_lane(tier):
        rows = tier["rows"]
        if view.get("eligible_only"):
            rows = [row for row in rows if row["eligible"]] or rows
        return rows[0]["lane"] if rows else None

    def tier_of(lane):
        for index, tier in enumerate(tiers):
            if any(row["lane"] == lane for row in tier["rows"]):
                return index
        return 0

    if key == "?":
        view["help"] = not view.get("help", False)
        return True
    if view.get("help"):
        if key == "\x1b":
            view["help"] = False
            return True
        return False
    if key in ("1", "2", "3", "4"):
        for tier in tiers:
            if tier["tier"] == int(key):
                view.setdefault("folded", set()).discard(tier["tier"])
                return first_lane(tier) or True
        return True
    if key in ("[", "]"):
        if not tiers:
            return True
        step = -1 if key == "[" else 1
        index = max(0, min(len(tiers) - 1, tier_of(selected) + step))
        view.setdefault("folded", set()).discard(tiers[index]["tier"])
        return first_lane(tiers[index]) or True
    if key == "e":
        view["eligible_only"] = not view.get("eligible_only", False)
        view["last_selected"] = None
        return True
    if key == "z":
        folded = view.setdefault("folded", set())
        number = tiers[tier_of(selected)]["tier"] if tiers else None
        if number is not None:
            folded.symmetric_difference_update({number})
        return True
    if key == "Z":
        folded = view.setdefault("folded", set())
        number = tiers[tier_of(selected)]["tier"] if tiers else None
        others = {tier["tier"] for tier in tiers} - {number}
        view["folded"] = set() if folded >= others else others
        return True
    if key in ("\x1b[6~", " "):
        view["offset"] = view.get("offset", 0) + 8
        return True
    if key == "\x1b[5~":
        view["offset"] = max(0, view.get("offset", 0) - 8)
        return True
    if key == "G":
        view["offset"] = max(0, view.get("items", 1) - 1)
        return True
    if key == "0":
        view["offset"] = 0
        return True
    return False
