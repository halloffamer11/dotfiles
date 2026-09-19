#!/usr/bin/env python3
"""PROTOTYPE: the `deck` layout, merged from Orin's verdict on panel and strip.

Throwaway.  A tote board for one project: one Lane to a row, Tiers stacked as
decks behind a coloured rail on the left edge.

Kept from ``panel``: the vertical coloured Tier line at the left edge, the
terminal's own background, and Remaining drawn as a solid rectangle.  Kept from
``strip``: the quiet palette with gold for the selected Lane, the icon in the
first content column, a top row naming the leading model of each Tier, and the
fixed top-right block for Gate, Margin, Meters and usage.

The three identity columns are separated by a box rule rather than a space, so
``Luna 5.6 | H | Codex`` reads as one plate and never as a sentence.  The deck
keeps a readable measure: past ``MEASURE`` cells the extra pane stays quiet
instead of stretching a row, and the Remaining bar takes the slack below it,
because Remaining is the value the Gate acts on.

Standard library only.  Host-owned keys are not handled here.
"""

from __future__ import annotations

import os
import unicodedata
from typing import Any


NAME = "deck"

NERD = os.environ.get("DELEGATE_DASHBOARD_NERD") == "1"
LIGHT = os.environ.get("DELEGATE_DASHBOARD_THEME") == "light"

RESET = "\033[0m"

# The deck's measure.  The grid below adds up to exactly this, so a column
# starts on the same cell at 100, 132 and 170.  A wider pane keeps quiet space
# rather than stretching a row past a readable measure; the header's right-hand
# block still follows the true pane edge, so the pane reads as one surface.
MEASURE = 100

DARK = {
    "fg": "#D8D4CA",
    "mute": "#7A7E6E",
    "gold": "#E6B84D",
    "veto": "#C45C4A",
    "steal": "#6DB3A8",
    "ok": "#7FBF6B",
    "watch": "#D9A441",
    "selbg": "#2C3340",
}
LIGHT_ROLES = {
    "fg": "#2A2E28",
    "mute": "#6E7268",
    "gold": "#8A5A00",
    "veto": "#A33B32",
    "steal": "#1F6F68",
    "ok": "#2F7D2B",
    "watch": "#8A5D00",
    "selbg": "#D9E0D2",
}
RAIL_DARK = {1: "#5FB37A", 2: "#2FA8B8", 3: "#C08A3E", 4: "#A97BD1"}
RAIL_LIGHT = {1: "#2E7D50", 2: "#17707C", 3: "#8A5D14", 4: "#6E4699"}

PAL = LIGHT_ROLES if LIGHT else DARK
RAILS = RAIL_LIGHT if LIGHT else RAIL_DARK

# Nerd Codicons behind the switch; the fallbacks hold the same one cell.
_NERD_GLYPHS = {
    "pick": "",
    "veto": "",
    "unknown": "",
    "steal": "",
    "carried": "",
    "order_p": "",
    "order_g": "",
    "folded": "",
    "open": "",
}
_PLAIN_GLYPHS = {
    "pick": "*",
    "veto": "!",
    "unknown": "?",
    "steal": "^",
    "carried": "·",
    "order_p": "p",
    "order_g": "g",
    "folded": "▸",
    "open": "▾",
}

RAIL = "▌"
RULE = "│"
LEADER = "◆"
BAR_FULL = "█"
BAR_PART = " ▏▎▍▌▋▊▉"
BAR_EMPTY = "·"
BAR_UNKNOWN = "╌"
EMDASH = "—"
TIMES = "×"

# Forced one cell: the marks the grid's alignment depends on.
_ONE_CELL = frozenset(
    list(_NERD_GLYPHS.values())
    + list(_PLAIN_GLYPHS.values())
    + [RAIL, RULE, LEADER, BAR_FULL, BAR_EMPTY, BAR_UNKNOWN, EMDASH, TIMES]
    + list(BAR_PART)
)

EFFORT = {"low": "L", "medium": "M", "high": "H", "xhigh": "XH", "max": "Max", "ultra": "U"}

# The closed reason set.  Every `reason` rank.py writes maps into one of these.
CODES = (
    ("PICK", "ranking selects this Lane for the next job"),
    ("STEAL", "takes the job from the Pick on Pace"),
    ("ELIG", "eligible; ranking sorts it after the Pick"),
    ("NOMTR", "no Meter reading, so it sorts last"),
    ("GATE", "Remaining is under the Gate"),
    ("CLI", "the harness is not on PATH"),
    ("FLOOR", "below the Class floor"),
    ("CEIL", "above the Class ceiling"),
    ("VETO", "held back for another reason"),
)

# 4b: the five values that earn a description.
TERMS = (
    ("Remaining", "the fraction of a Meter still unspent"),
    ("Pace", "affordable rate ÷ an even weekly spend"),
    ("Gate", "lowest Remaining that still takes a job"),
    ("Margin", "extra Pace needed to take the Pick's job"),
    ("Meter", "one subscription quota; Lanes share it"),
)

KEYS = (
    ("d", "descriptions on or off"),
    ("h", "Tier view or Harness view"),
    ("z", "fold the deck under the cursor"),
    ("?", "close this help"),
)

# name, width, alignment.  One space between every column; the widths and the
# gaps add up to MEASURE.  The bar takes the largest share, because Remaining
# is the value the Gate acts on and is the one loud thing on the deck.
PLAN = (
    ("rail", 1, "<"),
    ("icon", 1, "<"),
    ("ord", 3, ">"),
    ("model", 14, "<"),
    ("sep1", 1, "<"),
    ("effort", 3, "<"),
    ("sep2", 1, "<"),
    ("harness", 7, "<"),
    ("meter", 14, "<"),
    ("rem", 4, ">"),
    ("bar", 26, "<"),
    ("pace", 6, ">"),
    ("code", 7, "<"),
)
LABELS = {
    "ord": "Ord",
    "model": "Model",
    "sep1": RULE,
    "sep2": RULE,
    "effort": "Eff",
    "harness": "Harness",
    "meter": "Meter",
    "rem": "Rem",
    "bar": "Remaining",
    "pace": "Pace",
    "code": "Reason",
}
# Dropped in this order as the pane narrows; rail, icon and model never go.
DROPS = (
    ("code",),
    ("pace",),
    ("meter",),
    ("bar",),
    ("rem",),
    ("harness", "sep2"),
    ("effort", "sep1"),
    ("ord",),
)
# Given back in this order, the bar first, when a drop leaves the deck short.
GROWS = (("bar", 26), ("model", 8), ("meter", 6))

VENDORS = frozenset({"gpt", "claude", "gemini", "grok", "openai", "anthropic", "google", "xai"})
_EFFORT_WORDS = frozenset(EFFORT) | {"latest", "preview"}


def glyph(key: str) -> str:
    return (_NERD_GLYPHS if NERD else _PLAIN_GLYPHS)[key]


# --- terminal cells ---------------------------------------------------------


def _cell_width(char: str) -> int:
    if not char or unicodedata.combining(char):
        return 0
    if char in _ONE_CELL:
        return 1
    if unicodedata.category(char) in {"Cc", "Cf"}:
        return 0
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def cells(text: str) -> int:
    """Visible terminal cells, not Python characters."""
    return sum(_cell_width(char) for char in text)


def fit(text: str, width: int) -> str:
    """Clip to `width` cells, marking a clipped string with an ellipsis."""
    if width <= 0:
        return ""
    if cells(text) <= width:
        return text
    if width == 1:
        return "…"
    kept: list[str] = []
    used = 0
    for char in text:
        step = _cell_width(char)
        if used + step > width - 1:
            break
        kept.append(char)
        used += step
    return "".join(kept) + "…"


def pad(text: str, width: int, align: str = "<") -> str:
    text = fit(text, width)
    gap = max(0, width - cells(text))
    return (" " * gap + text) if align == ">" else (text + " " * gap)


def _sgr(hex_color: str, *, back: bool = False) -> str:
    value = hex_color.removeprefix("#")
    lead = 48 if back else 38
    return f"\033[{lead};2;{int(value[0:2], 16)};{int(value[2:4], 16)};{int(value[4:6], 16)}m"


def line(segments, width: int, *, back: str | None = None) -> str:
    """Paint (text, colour, bold) segments into at most `width` cells."""
    out: list[str] = []
    used = 0
    back_code = _sgr(back, back=True) if back else ""
    for text, color, bold in segments:
        if used >= width:
            break
        piece = fit(text, width - used)
        if not piece:
            continue
        out.append(
            ("\033[1m" if bold else "") + back_code + _sgr(color or PAL["fg"]) + piece + RESET
        )
        used += cells(piece)
    if back is not None and used < width:
        out.append(back_code + " " * (width - used) + RESET)
    return "".join(out)


# --- reading the state ------------------------------------------------------


def percent(value: Any) -> str:
    return EMDASH if value is None else f"{round(float(value) * 100):g}%"


def pace_text(value: Any) -> str:
    return EMDASH if value is None else f"{float(value):.2f}{TIMES}"


def bar(value: Any, width: int) -> str:
    """Remaining as one solid rectangle; an unknown Meter draws a dashed rule."""
    if width <= 0:
        return ""
    if value is None:
        return BAR_UNKNOWN * width
    filled = max(0.0, min(1.0, float(value))) * width
    full = int(filled)
    text = BAR_FULL * min(full, width)
    if full < width:
        eighths = int((filled - full) * 8)
        text += BAR_PART[eighths] if eighths else BAR_EMPTY
        text += BAR_EMPTY * (width - full - 1)
    return text[:width]


def display_model(row: dict[str, Any]) -> str:
    """The Lane's published name when the state carries one, else one slug rule.

    The rule: drop a leading vendor word, join the leading numbers into one
    version, drop a date and an effort word, and put the surviving name first.
    ``gpt-5.6-luna`` becomes ``Luna 5.6``; a slug with no name of its own, like
    ``grok-4.6``, keeps its vendor word.
    """
    published = row.get("published_as")
    if isinstance(published, (list, tuple)) and published:
        return str(published[0])
    slug = str(row.get("model") or "")
    if not slug:
        return EMDASH
    tokens = [token for token in slug.replace("_", "-").split("-") if token]
    vendor = tokens.pop(0) if tokens and tokens[0].lower() in VENDORS else ""
    numbers: list[str] = []
    words: list[str] = []
    for token in tokens:
        if token[0].isdigit():
            if len(token) < 5:  # a longer run is a build date, not a version
                numbers.append(token)
            continue
        if token.lower() in _EFFORT_WORDS:
            continue
        words.append(token)
    name = " ".join(word.capitalize() for word in words) or vendor.capitalize()
    version = ".".join(numbers)
    return f"{name} {version}".strip() or slug


def effort_letter(row: dict[str, Any]) -> str:
    effort = str(row.get("effort") or "")
    return EFFORT.get(effort, effort[:3].upper() or EMDASH)


def harness_name(row_or_name: Any) -> str:
    name = row_or_name.get("harness") if isinstance(row_or_name, dict) else row_or_name
    return str(name or "").capitalize() or EMDASH


def reason_code(row: dict[str, Any]) -> tuple[str, str]:
    """One code from the closed set, with the colour the scale gives it."""
    reason = str(row.get("reason") or "")
    if reason == "pick":
        return "PICK", PAL["gold"]
    if reason.startswith("stolen by pace"):
        return "STEAL", PAL["steal"]
    if reason.startswith("unknown meter") or row.get("remaining") is None:
        return "NOMTR", PAL["mute"]
    if reason.startswith("vetoed:gate"):
        return "GATE", PAL["veto"]
    if reason.startswith("vetoed:cli"):
        return "CLI", PAL["veto"]
    if reason.startswith("vetoed:floor"):
        return "FLOOR", PAL["mute"]
    if reason.startswith("vetoed:ceiling"):
        return "CEIL", PAL["mute"]
    if reason.startswith("vetoed:"):
        return "VETO", PAL["veto"]
    return "ELIG", PAL["fg"]


def status_icon(row: dict[str, Any]) -> tuple[str, str]:
    code, color = reason_code(row)
    if code == "PICK":
        return glyph("pick"), color
    if code == "STEAL":
        return glyph("steal"), color
    if code == "NOMTR":
        return glyph("unknown"), color
    if code in ("GATE", "CLI", "VETO", "FLOOR", "CEIL"):
        return glyph("veto"), color
    return glyph("carried"), PAL["mute"]


def remaining_color(row: dict[str, Any], state: dict[str, Any]) -> str:
    """Colour Remaining by what the Gate does with it, not by how large it is."""
    remaining = row.get("remaining")
    if remaining is None:
        return PAL["mute"]
    gate = ((state.get("policy") or {}).get("gate") or {}).get("value") or 0.0
    pace = row.get("pace")
    if remaining < gate:
        return PAL["veto"]
    if remaining < 2 * gate or (pace is not None and pace < 0.5):
        return PAL["watch"]
    return PAL["ok"]


def order_mark(row: dict[str, Any], state: dict[str, Any]) -> str:
    source = row.get("order_source")
    if not source:
        return " "
    project = (state.get("project") or {}).get("policy")
    return glyph("order_p") if source == project else glyph("order_g")


def leader_label(state: dict[str, Any], lane: Any) -> str:
    """Name the leading model, not the Lane, so no row repeats `name@harness`."""
    for tier in state.get("tiers") or []:
        for row in tier.get("rows") or []:
            if row.get("lane") == lane:
                return f"{display_model(row)} {effort_letter(row)}"
    return str(lane or "")


# --- the decks --------------------------------------------------------------


def groups(state: dict[str, Any], view: dict[str, Any]) -> list[dict[str, Any]]:
    """One deck per Tier, or per Harness and Tier inside it in the Harness view."""
    tiers = state.get("tiers") or []
    out: list[dict[str, Any]] = []
    if not view.get("harness_view"):
        for tier in tiers:
            number = tier.get("tier")
            out.append({
                "key": f"T{number}",
                "tier": number,
                "head": f"Tier {number}",
                "leader": tier.get("leader"),
                "rows": list(tier.get("rows") or []),
            })
        return out
    buckets: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    leaders: dict[tuple[str, Any], Any] = {}
    for tier in tiers:
        for row in tier.get("rows") or []:
            key = (str(row.get("harness") or ""), tier.get("tier"))
            buckets.setdefault(key, []).append(row)
            if row.get("lane") == tier.get("leader"):
                leaders[key] = tier.get("leader")
    for harness, number in sorted(buckets, key=lambda key: (key[0], key[1] is None, key[1])):
        out.append({
            "key": f"{harness}/T{number}",
            "tier": number,
            "head": f"{harness_name(harness)}  Tier {number}",
            "leader": leaders.get((harness, number)),
            "rows": buckets[(harness, number)],
        })
    return out


def entries(state: dict[str, Any], view: dict[str, Any]) -> list[tuple[str, Any, dict]]:
    """Flatten the decks into paintable items, honouring the folds."""
    folded = set(view.get("folded") or ())
    items: list[tuple[str, Any, dict]] = []
    for group in groups(state, view):
        items.append(("head", None, group))
        if group["key"] in folded:
            continue
        for row in group["rows"]:
            items.append(("lane", row, group))
    return items


def selectable(state: dict[str, Any], view: dict[str, Any]) -> list[str]:
    """The Lane names j/k may walk.

    A folded deck keeps exactly one name, so one press leaves it and the hidden
    rows are never walked.  The host paints that Lane's deck head as selected.
    """
    if not isinstance(view, dict):
        view = {}
    folded = set(view.get("folded") or ())
    names: list[str] = []
    for group in groups(state, view):
        rows = group["rows"]
        if not rows:
            continue
        if group["key"] in folded:
            names.append(rows[0]["lane"])
        else:
            names.extend(row["lane"] for row in rows)
    return names


def _group_of(state: dict[str, Any], view: dict[str, Any], lane: Any) -> dict[str, Any] | None:
    for group in groups(state, view):
        if any(row.get("lane") == lane for row in group["rows"]):
            return group
    return None


def _stop_lane(state: dict[str, Any], view: dict[str, Any], lane: Any) -> Any:
    """The selectable Lane that stands for `lane` once the folds are applied."""
    group = _group_of(state, view, lane)
    if group is None or group["rows"] is None:
        return lane
    if group["key"] in set(view.get("folded") or ()) and group["rows"]:
        return group["rows"][0]["lane"]
    return lane


# --- the grid ---------------------------------------------------------------


def grid(width: int) -> list[tuple[str, int, str]]:
    """Drop, then grow, and return the columns this pane can hold."""
    deck = max(0, min(int(width), MEASURE))
    columns = [[key, size, align] for key, size, align in PLAN]

    def spent(cols):
        return sum(size for _key, size, _align in cols) + max(0, len(cols) - 1)

    for group in DROPS:
        if spent(columns) <= deck:
            break
        columns = [column for column in columns if column[0] not in group]
    slack = deck - spent(columns)
    if slack < 0:
        for column in columns:
            if column[0] == "model":
                column[1] = max(3, column[1] + slack)
        return [(key, size, align) for key, size, align in columns]
    keys = {column[0] for column in columns}
    for key, most in GROWS:
        if not slack or key not in keys:
            continue
        take = min(slack, most)
        for column in columns:
            if column[0] == key:
                column[1] += take
        slack -= take
    return [(key, size, align) for key, size, align in columns]


def deck_width(columns) -> int:
    return sum(size for _key, size, _align in columns) + max(0, len(columns) - 1)


def lane_segments(row, group, state, columns, *, selected):
    """One Lane on the grid; every cell starts at the same column on every row."""
    code, code_color = reason_code(row)
    icon, icon_color = status_icon(row)
    rem_color = remaining_color(row, state)
    is_pick = code == "PICK"
    order = row.get("order")
    name_color = PAL["gold"] if (selected or is_pick) else PAL["fg"]
    values = {
        "rail": (RAIL, RAILS.get(group.get("tier"), PAL["mute"]), False),
        "icon": (icon, icon_color, is_pick),
        "ord": (f"{EMDASH if order is None else order}{order_mark(row, state)}", PAL["mute"], False),
        "model": (display_model(row), name_color, selected or is_pick),
        "sep1": (RULE, PAL["mute"], False),
        "effort": (effort_letter(row), name_color, False),
        "sep2": (RULE, PAL["mute"], False),
        "harness": (harness_name(row), name_color, False),
        "meter": (str(row.get("meter") or ""), PAL["mute"], False),
        "rem": (percent(row.get("remaining")), rem_color, False),
        "bar": (None, rem_color, False),
        "pace": (pace_text(row.get("pace")), rem_color, False),
        "code": (code, code_color, is_pick),
    }
    segments = []
    for index, (key, size, align) in enumerate(columns):
        if index:
            segments.append((" ", PAL["mute"], False))
        text, color, bold = values[key]
        if key == "bar":
            text = bar(row.get("remaining"), size)
        segments.append((pad(text, size, align), color, bold))
    return segments


def head_segments(group, state, view, width, *, selected):
    """The deck's own line: the fold mark, its name, its leading model, its count."""
    folded = group["key"] in set(view.get("folded") or ())
    rows = group["rows"]
    eligible = sum(1 for row in rows if row.get("eligible"))
    mark = glyph("folded") if folded else glyph("open")
    left = f"{RAIL} {mark} {group['head']}   "
    if group["leader"]:
        lead = f"{LEADER} {leader_label(state, group['leader'])}"
        lead_color = PAL["gold"]
    else:
        # In the Harness view a deck can hold eligible Lanes and still not hold
        # its Tier's leader, so only an empty deck is called none eligible.
        lead = f"{LEADER} none eligible" if not eligible else EMDASH
        lead_color = PAL["mute"]
    tail = f"{len(rows)} Lane{'' if len(rows) == 1 else 's'} · {eligible} eligible"
    gap = max(1, width - cells(left) - cells(lead) - cells(tail))
    return [
        (RAIL, RAILS.get(group.get("tier"), PAL["mute"]), False),
        (left[1:], PAL["gold"] if selected else PAL["fg"], True),
        (lead, PAL["gold"] if selected else lead_color, False),
        (" " * gap, PAL["mute"], False),
        (tail, PAL["mute"], False),
    ]


# --- chrome -----------------------------------------------------------------


def header_lines(state, width):
    """The identity row with the fixed top-right block, then the leaders row."""
    policy = state.get("policy") or {}
    gate = (policy.get("gate") or {}).get("display") or EMDASH
    margin = (policy.get("margin") or {}).get("display") or EMDASH
    meters = policy.get("meters") or {}
    meters_off = meters.get("value") is False
    meters_text = meters.get("display") or ("off" if meters_off else "on")
    usage = str((state.get("usage") or {}).get("status") or "")
    block = f"Gate {gate}  Margin {margin}  Meters {meters_text}  usage {usage}"
    project = str((state.get("project") or {}).get("name") or "")
    if cells(block) + 12 > width:
        block = f"G {gate}  M {margin}"
    room = max(0, width - cells(block) - 2)
    identity = [
        (pad(project, room), PAL["fg"], True),
        ("  ", PAL["mute"], False),
        (block, PAL["watch"] if meters_off else PAL["mute"], False),
    ]

    leaders = []
    for tier in state.get("tiers") or []:
        number = tier.get("tier")
        leaders.append((f"T{number} ", RAILS.get(number, PAL["mute"]), True))
        if tier.get("leader"):
            leaders.append((f"{LEADER} {leader_label(state, tier['leader'])}   ", PAL["fg"], False))
        else:
            leaders.append((f"{EMDASH}   ", PAL["mute"], False))
    return identity, leaders


def column_header(columns):
    segments = []
    for index, (key, size, align) in enumerate(columns):
        if index:
            segments.append((" ", PAL["mute"], False))
        segments.append((pad(LABELS.get(key, ""), size, align), PAL["mute"], False))
    return segments


def description_lines(width):
    """4b: the five values, each with the description `d` turns on and off."""
    written = [f"{pad(term, 9)}  {text}" for term, text in TERMS]
    if width >= 106:
        return [
            [(" ".join(pad(text, 51) for text in written[index : index + 2]), PAL["mute"], False)]
            for index in range(0, len(written), 2)
        ]
    return [[(text, PAL["mute"], False)] for text in written]


def help_lines(width):
    out = [[("deck · reason codes", PAL["fg"], True)]]
    for code, meaning in CODES:
        out.append([(f"  {pad(code, 7)}", PAL["gold"], False), (meaning, PAL["mute"], False)])
    out.append([("keys", PAL["fg"], True)])
    for key, meaning in KEYS:
        out.append([(f"  {pad(key, 7)}", PAL["gold"], False), (meaning, PAL["mute"], False)])
    out.append([
        ("  host   ", PAL["mute"], False),
        ("j/k select  J/K move inside the Tier  g/m edit  r reload  v next  q close",
         PAL["mute"], False),
    ])
    return out


HINTS = ("j/k select", "J/K move", "d descriptions", "h Harness view", "z fold")


def footer_line(state, view, editor, width):
    """The editor lives here, so opening it never moves the deck."""
    tail = f"layout: {NAME} (v next)"
    if editor is not None:
        field = str(getattr(editor, "field", "") or "gate")
        text = str(getattr(editor, "text", "") or "")
        head = f"{field.title()}  [ {text}_ ]%   ↵ save   esc cancel"
        color, bold = PAL["fg"], True
    elif view.get("message"):
        head, color, bold = str(view["message"]), PAL["watch"], False
    elif state.get("error"):
        head, color, bold = str(state["error"]), PAL["veto"], True
    elif (state.get("save") or {}).get("status") not in (None, "idle") and (
        state.get("save") or {}
    ).get("detail"):
        saved = state["save"]["status"] == "saved"
        head, color, bold = str(state["save"]["detail"]), PAL["ok"] if saved else PAL["veto"], not saved
    else:
        hints = list(HINTS)
        head = "  ".join(hints + ["? help"])
        while hints and cells(head) > width - cells(tail) - 3:
            hints.pop()
            head = "  ".join(hints + ["? help"])
        color, bold = PAL["mute"], False
    gap = max(1, width - cells(head) - cells(tail))
    return [(head, color, bold), (" " * gap, PAL["mute"], False), (tail, PAL["mute"], False)]


# --- the frame --------------------------------------------------------------


def render(state, *, width, height, selected_lane, editor, message, view):
    """Return exactly `height` painted strings, each at most `width` cells."""
    if not isinstance(view, dict):
        view = {}
    width = max(0, int(width))
    height = max(0, int(height))
    if height == 0:
        return []
    view["message"] = message or ""
    view["_selected"] = selected_lane

    columns = grid(width)
    deck = min(width, deck_width(columns))
    footer = line(footer_line(state, view, editor, width), width)
    if height == 1:
        return [footer]
    identity, leaders = header_lines(state, width)
    if height == 2:
        return [line(identity, width), footer]

    chrome = [line(identity, width), line(leaders, width)]
    if view.get("help"):
        body_height = height - len(chrome) - 1
        body = [line(part, width) for part in help_lines(width)][:body_height]
        body.extend([""] * max(0, body_height - len(body)))
        return chrome + body + [footer]

    chrome.append(line(column_header(columns), deck))
    if view.get("descriptions"):
        # A wider pane buys a shorter block, not a wider deck.
        chrome.extend(line(part, width) for part in description_lines(width))
    body_height = height - len(chrome) - 1
    if body_height < 1:
        painted = [line(identity, width), footer]
        painted.extend([""] * max(0, height - len(painted)))
        return painted[:height]

    items = entries(state, view)
    folded = set(view.get("folded") or ())
    index = None
    for position, (kind, row, group) in enumerate(items):
        if kind == "lane" and row.get("lane") == selected_lane:
            index = position
            break
        if (
            kind == "head"
            and index is None
            and group["key"] in folded
            and any(candidate.get("lane") == selected_lane for candidate in group["rows"])
        ):
            index = position
    offset = min(max(0, int(view.get("offset") or 0)), max(0, len(items) - body_height))
    if index is not None:
        if index < offset:
            offset = index
        elif index >= offset + body_height:
            offset = index - body_height + 1
    view["offset"] = offset
    view["_items"] = len(items)

    body = []
    for kind, row, group in items[offset : offset + body_height]:
        if kind == "head":
            here = group["key"] in folded and any(
                candidate.get("lane") == selected_lane for candidate in group["rows"]
            )
            body.append(
                line(
                    head_segments(group, state, view, deck, selected=here),
                    deck,
                    back=PAL["selbg"] if here else None,
                )
            )
            continue
        selected = row.get("lane") == selected_lane
        body.append(
            line(
                lane_segments(row, group, state, columns, selected=selected),
                deck,
                back=PAL["selbg"] if selected else None,
            )
        )
    body.extend([""] * max(0, body_height - len(body)))
    painted = chrome + body + [footer]
    painted.extend([""] * max(0, height - len(painted)))
    return painted[:height]


def handle_key(key, state, view):
    """Descriptions, the Harness view, folding and help.

    A Lane name returned here asks the host to select that Lane; it is truthy,
    so a host that only tests the result still reads it as "key used".
    """
    if not isinstance(view, dict):
        return False
    selected = view.get("_selected")
    if key == "?":
        view["help"] = not view.get("help", False)
        return True
    if view.get("help"):
        if key == "\x1b":
            view["help"] = False
            return True
        return False
    if key == "d":
        view["descriptions"] = not view.get("descriptions", False)
        return True
    if key == "h":
        view["harness_view"] = not view.get("harness_view", False)
        return _stop_lane(state, view, selected) or True
    if key == "z":
        group = _group_of(state, view, selected)
        if group is None:
            return True
        folded = set(view.get("folded") or ())
        folded.symmetric_difference_update({group["key"]})
        view["folded"] = folded
        # Folding puts the selection on the deck's own line, which the head row
        # paints; the first Lane of the deck is the one name that stands for it.
        return _stop_lane(state, view, selected) or True
    return False
