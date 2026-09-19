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
    "project": "",
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
    "project": "P",
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
MARK = "┃"  # the Gate on a Remaining bar, the steal threshold on a Pace bar
HAIRLINE = "─"
EMDASH = "—"
TIMES = "×"
ARROW = "→"

# Forced one cell: the marks the grid's alignment depends on.
_ONE_CELL = frozenset(
    list(_NERD_GLYPHS.values())
    + list(_PLAIN_GLYPHS.values())
    + [RAIL, RULE, LEADER, BAR_FULL, BAR_EMPTY, BAR_UNKNOWN, MARK, HAIRLINE,
       EMDASH, TIMES, ARROW]
    + list(BAR_PART)
)

EFFORT = {"low": "L", "medium": "M", "high": "H", "xhigh": "XH", "max": "Max", "ultra": "U"}

# The closed reason set.  Every `reason` rank.py writes maps into one of these,
# and each one is written out at the foot of the pane in its own colour.
CODES = (
    ("PICK", "gold", "Ranking selects this Lane for the next job."),
    ("STEAL", "steal", "Its Pace took the job from the Lane that sorted ahead of it."),
    ("ELIG", "fg", "Eligible. It sorts after the Pick and takes the job if the Pick cannot."),
    ("NOMTR", "mute", "Its Meter has no reading, so ranking sorts it last."),
    ("GATE", "veto", "Its Meter's Remaining is under the Gate, so it takes no job."),
    ("CLI", "veto", "Its harness is not on PATH, so nothing can run it here."),
    ("FLOOR", "mute", "Its Tier is below the floor of the Class asking for a Lane."),
    ("CEIL", "mute", "Its Tier is above the ceiling of the Class asking for a Lane."),
    ("VETO", "veto", "Held back for another reason the pane has no code for."),
)

# The five values that earn a description, in the words of CONTEXT.md.
TERMS = (
    ("Remaining", "The fraction of a Meter still unspent, using the lower Window "
                  "fraction when both Windows constrain the same spend."),
    ("Pace", "The rate a Meter can afford from now to its weekly reset, divided by "
             "an even spend across the whole week. 1.00× is on track, and above 1 "
             "means quota will expire unspent."),
    ("Gate", "The lowest Remaining a Meter may have and still take a job."),
    ("Margin", "How much higher a Lane's Pace must be to take a job from the Pick "
               "when it sorts after the Pick."),
    ("Meter", "One subscription quota. Each Lane uses exactly one, and many Lanes "
              "can share one."),
    ("Project Tier", "A Tier this project set for itself, in its own "
                     ".delegate/lanes.json. Every other project still sees the "
                     "Lane in the Tier the machine gives it. The mark in the T "
                     "column, and beside the Lane in the Harness table, says which "
                     "rows those are."),
)

# The three bodies, in the order Tab walks them.
VIEWS = ("list", "table", "aid")
VIEW_NAMES = {"list": "Tier list", "table": "Harness table", "aid": "Gate/Margin"}

KEYS = (
    ("Tab", "the next view: Tier list, Harness table, Gate/Margin"),
    ("a", "the Gate/Margin view, and back to the one before it"),
    ("h j k l", "move the selection; the arrow keys do the same"),
    ("H  L", "move the selected Lane one Tier left or right, for this project"),
    ("d", "the terms and every reason code, at the foot"),
    ("z", "fold the deck, or the Harness row, under the cursor"),
    ("?", "close this help"),
)

# Up and down never reach a variant: the host owns j, k and those two arrows,
# and walks `selectable`, which is already the spatial order of each view.
ARROWS = {"\x1b[C": "l", "\x1b[D": "h"}

# name, width, alignment.  One space between every column; the widths and the
# gaps add up to MEASURE.  The bar takes the largest share, because Remaining
# is the value the Gate acts on and is the one loud thing on the deck.
PLAN = (
    ("rail", 1, "<"),
    ("icon", 1, "<"),
    ("ord", 3, ">"),
    ("tsrc", 1, "<"),
    ("model", 14, "<"),
    ("sep1", 1, "<"),
    ("effort", 3, "<"),
    ("sep2", 1, "<"),
    ("harness", 7, "<"),
    ("meter", 14, "<"),
    ("rem", 4, ">"),
    ("bar", 24, "<"),
    ("pace", 6, ">"),
    ("code", 7, "<"),
)
LABELS = {
    "ord": "Ord",
    "tsrc": "T",
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
# Dropped in this order as the pane narrows; rail, icon, the project Tier mark
# and model never go: the mark says the Tier is not the one the machine sets.
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
GROWS = (("bar", 24), ("model", 8), ("meter", 6))

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
    """Paint (text, colour, bold) segments into at most `width` cells.

    A segment may carry a fourth item, its own background, which is how the
    Harness table bands one cell of a row rather than the whole row.
    """
    out: list[str] = []
    used = 0
    for segment in segments:
        text, color, bold = segment[0], segment[1], segment[2]
        behind = segment[3] if len(segment) > 3 else back
        if used >= width:
            break
        piece = fit(text, width - used)
        if not piece:
            continue
        out.append(
            ("\033[1m" if bold else "")
            + (_sgr(behind, back=True) if behind else "")
            + _sgr(color or PAL["fg"])
            + piece
            + RESET
        )
        used += cells(piece)
    if back is not None and used < width:
        out.append(_sgr(back, back=True) + " " * (width - used) + RESET)
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


CODE_ROLE = {code: role for code, role, _text in CODES}


def code_color(code: str) -> str:
    return PAL.get(CODE_ROLE.get(code, "fg"), PAL["fg"])


def reason_code(row: dict[str, Any]) -> tuple[str, str]:
    """One code from the closed set, with the colour the scale gives it."""
    reason = str(row.get("reason") or "")
    if reason == "pick":
        code = "PICK"
    elif reason.startswith("stolen by pace"):
        code = "STEAL"
    elif reason.startswith("unknown meter") or row.get("remaining") is None:
        code = "NOMTR"
    elif reason.startswith("vetoed:gate"):
        code = "GATE"
    elif reason.startswith("vetoed:cli"):
        code = "CLI"
    elif reason.startswith("vetoed:floor"):
        code = "FLOOR"
    elif reason.startswith("vetoed:ceiling"):
        code = "CEIL"
    elif reason.startswith("vetoed:"):
        code = "VETO"
    else:
        code = "ELIG"
    return code, code_color(code)


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


def project_tier(row: dict[str, Any]) -> bool:
    """True when this project, not the machine, put the Lane in this Tier."""
    return row.get("tier_source") == "project"


def tier_mark(row: dict[str, Any]) -> tuple[str, str]:
    """The quiet mark, and its colour, for a Tier this project set."""
    if not project_tier(row):
        return " ", PAL["mute"]
    return glyph("project"), PAL["watch"]


def leader_label(state: dict[str, Any], lane: Any) -> str:
    """Name the leading model, not the Lane, so no row repeats `name@harness`."""
    for tier in state.get("tiers") or []:
        for row in tier.get("rows") or []:
            if row.get("lane") == lane:
                return f"{display_model(row)} {effort_letter(row)}"
    return str(lane or "")


# --- the decks --------------------------------------------------------------


def groups(state: dict[str, Any], view: dict[str, Any]) -> list[dict[str, Any]]:
    """One deck per Tier: the Tier list's own unit, and what `z` folds there."""
    out: list[dict[str, Any]] = []
    for tier in state.get("tiers") or []:
        number = tier.get("tier")
        out.append({
            "key": f"T{number}",
            "tier": number,
            "head": f"Tier {number}",
            "leader": tier.get("leader"),
            "rows": list(tier.get("rows") or []),
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


def table(state: dict[str, Any]) -> tuple[list[str], list[Any], dict]:
    """The Harness table: Harnesses down the page, Tiers across it.

    Returns the Harness names, the Tier numbers, and the Lanes of each cell.
    """
    tiers = [tier.get("tier") for tier in state.get("tiers") or []]
    harnesses: list[str] = []
    cell: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for tier in state.get("tiers") or []:
        for row in tier.get("rows") or []:
            name = str(row.get("harness") or "")
            if name not in harnesses:
                harnesses.append(name)
            cell.setdefault((name, tier.get("tier")), []).append(row)
    harnesses.sort()
    return harnesses, tiers, cell


def table_order(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The table read down each Tier column in turn, which is how j/k walk it.

    Column by column keeps the Tier list's own sequence, so `h` never moves the
    selection, and `J`/`K` read as a move inside the column they are already in.
    """
    harnesses, tiers, cell = table(state)
    out: list[dict[str, Any]] = []
    for number in tiers:
        for name in harnesses:
            out.extend(cell.get((name, number)) or ())
    return out


def _harness_key(harness: Any) -> str:
    return f"H/{harness}"


def current_view(view: dict[str, Any]) -> str:
    """Which of the three bodies is showing."""
    name = view.get("view")
    return name if name in VIEWS else VIEWS[0]


def table_step(state: dict[str, Any], view: dict[str, Any], lane: Any, delta: int) -> Any:
    """`h` and `l` in the table: the nearest Lane one Tier column over.

    The same Harness row wins when it has a Lane in that column; otherwise the
    nearest row does, counting rows and preferring the one above on a tie.  A
    column with no Lane to stop on is stepped over, not stopped in, and inside
    the chosen cell the cursor keeps the line it was on as far as the cell goes.
    """
    harnesses, tiers, cell = table(state)
    allowed = set(selectable(state, view))
    here = None
    for tier_index, number in enumerate(tiers):
        for row_index, name in enumerate(harnesses):
            shown = [
                row["lane"] for row in (cell.get((name, number)) or ())
                if row["lane"] in allowed
            ]
            if lane in shown:
                here = (row_index, tier_index, shown.index(lane))
    if here is None:
        return None
    row_index, tier_index, depth = here
    step = tier_index + delta
    while 0 <= step < len(tiers):
        column: dict[int, list[str]] = {}
        for other, name in enumerate(harnesses):
            shown = [
                row["lane"] for row in (cell.get((name, tiers[step])) or ())
                if row["lane"] in allowed
            ]
            if shown:
                column[other] = shown
        if column:
            if row_index in column:
                found = column[row_index]
            else:
                nearest = min(column, key=lambda other: (abs(other - row_index), other))
                found = column[nearest]
            return found[min(depth, len(found) - 1)]
        step += delta
    return None


def selectable(state: dict[str, Any], view: dict[str, Any]) -> list[str]:
    """The Lane names j/k may walk, in the order the current view reads.

    A folded deck, or a folded Harness row, keeps exactly one name, so one press
    leaves it and the hidden rows are never walked.
    """
    if not isinstance(view, dict):
        view = {}
    folded = set(view.get("folded") or ())
    names: list[str] = []
    if current_view(view) == "table":
        seen: set[str] = set()
        for row in table_order(state):
            key = _harness_key(row.get("harness"))
            if key in folded:
                if key in seen:
                    continue
                seen.add(key)
            names.append(row["lane"])
        return names
    for group in groups(state, view):
        rows = group["rows"]
        if not rows:
            continue
        if group["key"] in folded:
            names.append(rows[0]["lane"])
        else:
            names.extend(row["lane"] for row in rows)
    return names


def _fold_key_of(state: dict[str, Any], view: dict[str, Any], lane: Any) -> str | None:
    """What `z` folds for this Lane: its Harness row, or its Tier's deck."""
    for tier in state.get("tiers") or []:
        for row in tier.get("rows") or []:
            if row.get("lane") == lane:
                if current_view(view) == "table":
                    return _harness_key(row.get("harness"))
                return f"T{tier.get('tier')}"
    return None


def _stop_lane(state: dict[str, Any], view: dict[str, Any], lane: Any) -> Any:
    """The selectable Lane that stands for `lane` once the folds are applied."""
    key = _fold_key_of(state, view, lane)
    if key is None or key not in set(view.get("folded") or ()):
        return lane
    if current_view(view) == "table":
        for row in table_order(state):
            if _harness_key(row.get("harness")) == key:
                return row["lane"]
        return lane
    for group in groups(state, view):
        if group["key"] == key and group["rows"]:
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
        "tsrc": tier_mark(row) + (False,),
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
        lead = f"{LEADER} none eligible"
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


# --- the Harness table ------------------------------------------------------

# label, then one Tier column each behind a rule in the Tier's own hue.
TABLE_LABEL = 9
TABLE_GUTTER = 2  # the coloured rule and the space after it


def table_cell_width(width: int, count: int) -> int:
    if count <= 0:
        return 0
    deck = max(0, min(int(width), MEASURE))
    return max(6, (deck - TABLE_LABEL) // count - TABLE_GUTTER)


def table_entry(row, size, *, selected):
    """One Lane in a cell: the icon, the model and the effort letter, no more.

    The selected Lane is banded across its own cell, which is what the Tier
    list bands across its whole row; gold carries it either way.
    """
    code, color = reason_code(row)
    icon, icon_color = status_icon(row)
    band = PAL["selbg"] if selected else None
    text = f"{display_model(row)} {effort_letter(row)}"
    # The cell keeps its width: the project Tier mark takes a cell of its own
    # between the icon and the name, so a Lane this project moved reads at a
    # glance and the names still start on the same column in every cell.
    mark, mark_color = tier_mark(row)
    return [
        (icon, PAL["gold"] if selected else icon_color, code == "PICK", band),
        (mark, mark_color, False, band),
        (" ", PAL["mute"], False, band),
        (pad(text, max(0, size - 3)), PAL["gold"] if selected else color,
         selected or code == "PICK", band),
    ]


def table_lines(state, view, width, selected_lane):
    """Harnesses down, Tiers across.  Each block is as tall as its fullest cell.

    Returns the painted segments and the line the selection sits on.  Colour is
    the only ink beyond the words: the rule down each column carries the Tier's
    hue, and each Lane carries its reason's.
    """
    harnesses, tiers, cell = table(state)
    folded = set(view.get("folded") or ())
    size = table_cell_width(width, len(tiers))
    out: list[list[tuple]] = []
    cursor = None

    head: list[tuple] = [(pad("", TABLE_LABEL), PAL["mute"], False)]
    for number in tiers:
        head.append((RULE, RAILS.get(number, PAL["mute"]), False))
        head.append((" ", PAL["mute"], False))
        head.append((pad(f"Tier {number}", size), RAILS.get(number, PAL["mute"]), True))
    out.append(head)

    for index, name in enumerate(harnesses):
        if index:
            out.append([])
        rows_here = [row for number in tiers for row in (cell.get((name, number)) or ())]
        here = any(row.get("lane") == selected_lane for row in rows_here)
        if _harness_key(name) in folded:
            eligible = sum(1 for row in rows_here if row.get("eligible"))
            if here:
                cursor = len(out)
            out.append([
                (pad(f"{glyph('folded')} {harness_name(name)}", TABLE_LABEL),
                 PAL["gold"] if here else PAL["fg"], True,
                 PAL["selbg"] if here else None),
                (f"{len(rows_here)} Lanes folded · {eligible} eligible",
                 PAL["gold"] if here else PAL["mute"], False,
                 PAL["selbg"] if here else None),
            ])
            continue
        depth = max((len(cell.get((name, number)) or ()) for number in tiers), default=0)
        for line_no in range(max(1, depth)):
            label = f"{glyph('open')} {harness_name(name)}" if line_no == 0 else ""
            segments: list[tuple] = [(pad(label, TABLE_LABEL), PAL["fg"], line_no == 0)]
            for number in tiers:
                column = cell.get((name, number)) or ()
                segments.append((RULE, RAILS.get(number, PAL["mute"]), False))
                segments.append((" ", PAL["mute"], False))
                if line_no < len(column):
                    row = column[line_no]
                    selected = row.get("lane") == selected_lane
                    if selected:
                        cursor = len(out)
                    segments.extend(table_entry(row, size, selected=selected))
                elif line_no == 0:
                    # An empty cell says so; blank space would read as a fault.
                    segments.append((pad(f"{EMDASH} none", size), PAL["mute"], False))
                else:
                    segments.append((pad("", size), PAL["mute"], False))
            out.append(segments)
    return out, cursor


# --- the Gate and Margin aid -------------------------------------------------


def meter_rows(state):
    """One entry per Meter: its Harness, its Remaining and Pace, and its Lanes."""
    order: list[str] = []
    seen: dict[str, dict[str, Any]] = {}
    for tier in state.get("tiers") or []:
        for row in tier.get("rows") or []:
            name = str(row.get("meter") or "")
            entry = seen.get(name)
            if entry is None:
                order.append(name)
                entry = seen[name] = {
                    "meter": name,
                    "harness": str(row.get("harness") or ""),
                    "remaining": row.get("remaining"),
                    "pace": row.get("pace"),
                    "lanes": [],
                }
            entry["lanes"].append(dict(row, _tier=tier.get("tier")))
    return [seen[name] for name in order]


def steal_thresholds(state):
    """``Pick's Pace + Margin`` per Tier: what a Lane must now reach to take it.

    The rule is rank.py's, lines 177-183: scanning the eligible Lanes after the
    first in sort order, a Lane takes the Pick when its Pace reaches the current
    Pick's Pace plus the Margin, and the Pick then moves to it, so the bar this
    draws is the one a further Lane has to clear.
    """
    margin = ((state.get("policy") or {}).get("margin") or {}).get("value") or 0.0
    out: dict[Any, dict[str, Any]] = {}
    for tier in state.get("tiers") or []:
        for row in tier.get("rows") or []:
            code, _color = reason_code(row)
            if code in ("PICK", "STEAL"):
                pace = row.get("pace")
                out[tier.get("tier")] = {
                    "pick": row.get("lane"),
                    "meter": row.get("meter"),
                    "pace": pace,
                    "threshold": None if pace is None else float(pace) + float(margin),
                }
                break
    return out


def meter_verdict(entry, state, thresholds):
    """What the Gate and the Margin do to this Meter, in one phrase each."""
    gate = ((state.get("policy") or {}).get("gate") or {}).get("value") or 0.0
    remaining = entry["remaining"]
    if remaining is None:
        rem_text, rem_color = "no Meter reading", PAL["mute"]
    elif float(remaining) < float(gate):
        # rank.py vetoes through usage.eligible: Remaining equal to Gate passes.
        rem_text, rem_color = "under the Gate", PAL["veto"]
    else:
        rem_text, rem_color = "over the Gate", PAL["ok"]

    pace = entry["pace"]
    holds = [number for number, item in thresholds.items() if item["meter"] == entry["meter"]]
    if holds:
        return (rem_text, rem_color,
                f"holds the Pick in T{min(holds)}", PAL["gold"])
    if rem_color is PAL["veto"]:
        # The Gate already vetoed it; the Margin never gets a say.
        return rem_text, rem_color, EMDASH, PAL["mute"]
    if pace is None:
        return rem_text, rem_color, "no Pace reading", PAL["mute"]
    reachable = [
        (item["threshold"], number)
        for number, item in thresholds.items()
        if item["threshold"] is not None
        and any(row["_tier"] == number and row.get("eligible") for row in entry["lanes"])
    ]
    if not reachable:
        return rem_text, rem_color, "no Tier it can take", PAL["mute"]
    threshold, number = min(reachable)
    if float(pace) >= threshold:
        return rem_text, rem_color, f"takes the Pick in T{number}", PAL["steal"]
    return (rem_text, rem_color,
            f"needs {threshold:.2f}{TIMES} to take T{number}", PAL["mute"])


def marked_bar(value, width, *, mark_at, scale=1.0, color, mark_color):
    """A solid bar with one threshold mark standing where the rule bites."""
    segments: list[tuple[str, str, bool]] = []
    if width <= 0:
        return segments
    position = None
    if mark_at is not None and scale > 0:
        position = int(round(float(mark_at) / float(scale) * width))
        position = None if position < 0 or position >= width else position
    exact = 0.0
    if value is not None and scale > 0:
        exact = max(0.0, min(1.0, float(value) / float(scale))) * width
    filled = int(exact)
    eighths = int((exact - filled) * 8)
    for index in range(width):
        if index == position:
            segments.append((MARK, mark_color, True))
        elif value is None:
            segments.append((BAR_UNKNOWN, PAL["mute"], False))
        elif index < filled:
            segments.append((BAR_FULL, color, False))
        elif index == filled and eighths:
            segments.append((BAR_PART[eighths], color, False))
        else:
            segments.append((BAR_EMPTY, PAL["mute"], False))
    return segments


def aid_lines(state, width):
    """Per Meter, under its Harness: Remaining against the Gate, Pace against
    the Pace a Lane must reach to take the Pick."""
    deck = max(0, min(int(width), MEASURE))
    policy = state.get("policy") or {}
    gate = (policy.get("gate") or {}).get("value") or 0.0
    gate_text = (policy.get("gate") or {}).get("display") or EMDASH
    margin_text = (policy.get("margin") or {}).get("display") or EMDASH
    thresholds = steal_thresholds(state)
    meters = meter_rows(state)
    paces = [entry["pace"] for entry in meters if entry["pace"] is not None]
    paces += [item["threshold"] for item in thresholds.values() if item["threshold"] is not None]
    scale = max(2.0, (max(paces) if paces else 0.0) * 1.15)

    bar_w = max(8, min(34, deck - 46))
    out: list[list[tuple[str, str, bool]]] = [
        [("How the Gate and the Margin act, per Meter", PAL["fg"], True)],
        [(f"A Lane is vetoed when its Meter's Remaining is under {MARK}, the Gate "
          f"at {gate_text}.", PAL["mute"], False)],
        [(f"A Lane takes the Pick when its Pace reaches {MARK}, the Pick's Pace plus "
          f"the Margin of {margin_text}.", PAL["mute"], False)],
    ]
    harness = None
    meters.sort(key=lambda entry: (entry["harness"], entry["meter"]))
    for entry in meters:
        if entry["harness"] != harness:
            harness = entry["harness"]
            out.append([])
            out.append([(harness_name(harness), PAL["fg"], True)])
        rem_text, rem_color, pace_text_, pace_color = meter_verdict(entry, state, thresholds)
        out.append(
            [("  " + pad(entry["meter"], 16), PAL["mute"], False),
             (pad("Rem", 5), PAL["mute"], False)]
            + marked_bar(entry["remaining"], bar_w, mark_at=gate, scale=1.0,
                         color=remaining_color(entry, state), mark_color=PAL["veto"])
            + [(" " + pad(percent(entry["remaining"]), 5, ">"), PAL["fg"], False),
               ("  " + rem_text, rem_color, False)]
        )
        reachable = [
            item["threshold"]
            for number, item in thresholds.items()
            if item["threshold"] is not None
            and any(row["_tier"] == number and row.get("eligible") for row in entry["lanes"])
        ]
        out.append(
            [(pad("", 18), PAL["mute"], False), (pad("Pace", 5), PAL["mute"], False)]
            + marked_bar(entry["pace"], bar_w, mark_at=min(reachable) if reachable else None,
                         scale=scale, color=PAL["steal"], mark_color=PAL["gold"])
            + [(" " + pad(pace_text(entry["pace"]), 5, ">"), PAL["fg"], False),
               ("  " + pace_text_, pace_color, False)]
        )
    return out


# --- the foot: descriptions and the reason codes ----------------------------


def wrapped(term, text, *, term_width, measure):
    """One term, then its sentence at a comfortable measure under one indent."""
    body = measure - term_width
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if cells(candidate) > body and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return [(pad(term, term_width), line_text) for term, line_text in
            [(term, lines[0])] + [("", rest) for rest in lines[1:]]]


def foot_lines(width):
    """The descriptions and every reason code, in plain words, at the foot."""
    measure = min(max(0, int(width)), 82)
    out: list[list[tuple[str, str, bool]]] = [
        [(HAIRLINE * min(max(0, int(width)), MEASURE), PAL["mute"], False)]
    ]
    for term, text in TERMS:
        for label, body in wrapped(term, text, term_width=14, measure=measure):
            out.append([(label, PAL["fg"], bool(label.strip())), (body, PAL["mute"], False)])
    out.append([])
    for code, role, text in CODES:
        for label, body in wrapped(code, text, term_width=8, measure=measure):
            out.append([(label, PAL.get(role, PAL["fg"]), bool(label.strip())),
                        (body, PAL["mute"], False)])
    return out


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


def help_lines(width):
    out = [[("deck", PAL["fg"], True),
            ("   a Lane is a model at an effort on a harness", PAL["mute"], False)]]
    for key, meaning in KEYS:
        out.append([(f"  {pad(key, 9)}", PAL["gold"], False), (meaning, PAL["mute"], False)])
    out.append([])
    out.append([("  host     ", PAL["mute"], False),
                ("j/k select  J/K move the Lane inside its Tier  g/m edit the Gate or "
                 "the Margin", PAL["mute"], False)])
    out.append([(pad("", 11), PAL["mute"], False),
                ("r reload  v next layout  q close", PAL["mute"], False)])
    out.append([])
    out.append([("  In the Tier list j/k walk the Lanes down the page and h/l close and "
                 "open a deck.", PAL["mute"], False)])
    out.append([("  In the Harness table j/k walk down one Tier column, so a Tier keeps "
                 "the sequence", PAL["mute"], False)])
    out.append([("  it has in the list, and h/l cross to the nearest Lane one column over, "
                 "keeping the", PAL["mute"], False)])
    out.append([("  same Harness row when that row has one.", PAL["mute"], False)])
    out.append([])
    out.append([("  J/K", PAL["gold"], False),
                ("  move the Lane inside its Tier's Order, which every Harness in that "
                 "Tier shares.", PAL["mute"], False)])
    out.append([("  H/L", PAL["gold"], False),
                ("  move it to the Tier left or right, for this project only. Both "
                 "save at once,", PAL["mute"], False)])
    out.append([(pad("", 7), PAL["mute"], False),
                ("and the line above says what changed. Tier 1 has nothing to its left "
                 "and", PAL["mute"], False)])
    out.append([(pad("", 7), PAL["mute"], False),
                ("Tier 4 nothing to its right.", PAL["mute"], False)])
    out.append([])
    out.append([(f"  {glyph('project')}  ", PAL["watch"], False),
                ("in the T column, or beside a Lane in the table, marks a Tier this "
                 "project set", PAL["mute"], False)])
    out.append([(pad("", 5), PAL["mute"], False),
                ("for itself. Every other project sees the machine's Tier.",
                 PAL["mute"], False)])
    return out


HINTS = {
    "list": ("j/k select", "h/l fold", "Tab Harness table", "d terms", "J/K move", "z fold"),
    "table": ("hjkl move", "HL Tier", "Tab Gate/Margin", "d terms", "J/K Order", "z fold"),
    "aid": ("Tab Tier list", "a back", "d terms"),
}


def footer_line(state, view, editor, width):
    """The editor lives here, so opening it never moves the deck."""
    tail = f"layout: {NAME} (v next)"
    if editor is not None:
        field = str(getattr(editor, "field", "") or "gate")
        text = str(getattr(editor, "text", "") or "")
        head = f"{field.title()}  [ {text}_ ]%   ↵ save   esc cancel"
        color, bold = PAL["fg"], True
    elif view.get("note") or view.get("order_note"):
        head, color, bold = str(view.get("note") or view["order_note"]), PAL["watch"], False
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
        hints = list(HINTS[current_view(view)])
        head = "  ".join(hints + ["? help"])
        while hints and cells(head) > width - cells(tail) - 3:
            hints.pop()
            head = "  ".join(hints + ["? help"])
        color, bold = PAL["mute"], False
    gap = max(1, width - cells(head) - cells(tail))
    return [(head, color, bold), (" " * gap, PAL["mute"], False), (tail, PAL["mute"], False)]


# --- the frame --------------------------------------------------------------


def _cell_position(state, view, lane):
    """(Tier, Order, the line the Lane sits on inside its cell), or None."""
    harnesses, tiers, cell = table(state)
    for number in tiers:
        for name in harnesses:
            rows = cell.get((name, number)) or ()
            for depth, row in enumerate(rows):
                if row.get("lane") == lane:
                    return number, row.get("order"), depth
    return None


def _watch_order(state, view, lane):
    """Say so when `J`/`K` really moved the Order but the table did not stir.

    Order belongs to the Tier, not to the Harness row, so the Lane that swapped
    places can be another Harness's.  The Tier list shows that move; the table's
    cell cannot, and silence there reads as a key that did nothing.
    """
    view["order_note"] = None
    if current_view(view) != "table" or lane is None:
        view["_order_seen"] = None
        return
    now = _cell_position(state, view, lane)
    before = view.get("_order_seen")
    view["_order_seen"] = (lane, now)
    if not before or before[0] != lane or before[1] is None or now is None:
        return
    tier, order, depth = now
    was_tier, was_order, was_depth = before[1]
    if tier == was_tier and order != was_order and depth == was_depth:
        view["order_note"] = (
            f"Order {was_order} {ARROW} {order} in Tier {tier}. The Tier's Order is shared "
            f"by every Harness, so the Lane that swapped is another Harness's and this "
            f"cell does not move."
        )


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

    _watch_order(state, view, selected_lane)

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

    # The foot takes what it needs and leaves the body at least three lines.
    foot: list[str] = []
    if view.get("descriptions"):
        room = max(0, height - len(chrome) - 1 - 3)
        foot = [line(part, width) for part in foot_lines(width)][:room]

    if current_view(view) == "aid":
        body_height = height - len(chrome) - len(foot) - 1
        if body_height < 1:
            painted = [line(identity, width), footer]
            painted.extend([""] * max(0, height - len(painted)))
            return painted[:height]
        body = [line(part, width) for part in aid_lines(state, width)][:body_height]
        body.extend([""] * max(0, body_height - len(body)))
        return chrome + body + foot + [footer]

    if current_view(view) == "table":
        body_height = height - len(chrome) - len(foot) - 1
        if body_height < 1:
            painted = [line(identity, width), footer]
            painted.extend([""] * max(0, height - len(painted)))
            return painted[:height]
        parts, cursor = table_lines(state, view, width, selected_lane)
        # The Tier row stays put; only the Harness blocks under it scroll.
        head, blocks = parts[0], parts[1:]
        cursor = None if cursor is None else cursor - 1
        window = max(1, body_height - 1)
        offset = min(max(0, int(view.get("offset") or 0)), max(0, len(blocks) - window))
        if cursor is not None:
            if cursor < offset:
                offset = cursor
            elif cursor >= offset + window:
                offset = cursor - window + 1
        view["offset"] = offset
        view["_items"] = len(blocks)
        body = [line(head, min(width, MEASURE))]
        body.extend(line(part, min(width, MEASURE)) for part in blocks[offset : offset + window])
        body = body[:body_height]
        body.extend([""] * max(0, body_height - len(body)))
        return chrome + body + foot + [footer]

    chrome.append(line(column_header(columns), deck))
    body_height = height - len(chrome) - len(foot) - 1
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
    painted = chrome + body + foot + [footer]
    painted.extend([""] * max(0, height - len(painted)))
    return painted[:height]


def _set_view(state, view, name):
    """Show one of the three bodies and keep the selection on a real stop."""
    view["view"] = name if name in VIEWS else VIEWS[0]
    view["offset"] = 0
    return _stop_lane(state, view, view.get("_selected"))


def _move_tier(state, view, model, delta):
    """`H`/`L`: move the selected Lane one Tier, for this project.

    The save is the model's and is immediate, the way `J`/`K` move the Order
    inside a Tier.  The model puts what it did, or why it could not, into the
    save state, which the footer draws; the two Tier edges are answered here so
    the pane never asks the catalog for a move it already knows is off the board.
    """
    selected = view.get("_selected")
    if model is None:
        view["note"] = "Tier moves need the host's save path; this build did not pass one."
        return True
    tier = None
    for item in state.get("tiers") or []:
        if any(row.get("lane") == selected for row in item.get("rows") or ()):
            tier = item.get("tier")
            break
    if tier is None:
        return True
    if tier + delta not in RAILS:
        view["note"] = (
            f"Tier {tier} is the {'first' if delta < 0 else 'last'} Tier; "
            f"{selected} cannot move {'left' if delta < 0 else 'right'}."
        )
        return True
    model.move_lane_tier(selected, delta)
    return True


def handle_key(key, state, view, model=None):
    """The views, the selection, folding, help, and the one Tier write.

    A Lane name returned here asks the host to select that Lane; it is truthy,
    so a host that only tests the result still reads it as "key used".  ``model``
    arrives only from a host that offers it, and only ``H``/``L`` use it.
    """
    if not isinstance(view, dict):
        return False
    selected = view.get("_selected")
    key = ARROWS.get(key, key)
    view["note"] = None
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
    if key == "\t":
        here = current_view(view)
        return _set_view(state, view, VIEWS[(VIEWS.index(here) + 1) % len(VIEWS)]) or True
    if key == "\x1b[Z":
        here = current_view(view)
        return _set_view(state, view, VIEWS[(VIEWS.index(here) - 1) % len(VIEWS)]) or True
    if key == "a":
        here = current_view(view)
        if here == "aid":
            return _set_view(state, view, view.get("_before_aid") or VIEWS[0]) or True
        view["_before_aid"] = here
        return _set_view(state, view, "aid") or True
    if key == "z":
        key_name = _fold_key_of(state, view, selected)
        if key_name is None:
            return True
        folded = set(view.get("folded") or ())
        folded.symmetric_difference_update({key_name})
        view["folded"] = folded
        # Folding puts the selection on the deck's, or the Harness row's, own
        # line; its first Lane is the one name that stands for the fold.
        return _stop_lane(state, view, selected) or True

    here = current_view(view)
    if here == "table":
        if key in ("h", "l"):
            found = table_step(state, view, selected, -1 if key == "h" else 1)
            if found is None:
                view["note"] = (
                    f"No Lane to the {'left' if key == 'h' else 'right'} of this column."
                )
                return True
            return found
        if key in ("H", "L"):
            return _move_tier(state, view, model, -1 if key == "H" else 1)
        return False
    if here == "list" and key in ("h", "l"):
        # In a list of decks, left closes and right opens, the way a tree does.
        key_name = _fold_key_of(state, view, selected)
        if key_name is None:
            return True
        folded = set(view.get("folded") or ())
        if key == "h":
            folded.add(key_name)
        else:
            folded.discard(key_name)
        view["folded"] = folded
        return _stop_lane(state, view, selected) or True
    return False
