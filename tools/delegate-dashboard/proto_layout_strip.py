#!/usr/bin/env python3
"""PROTOTYPE rank-strip layout for the delegate dashboard.

Tote-board: one Lane per row on a fixed character grid. Pick is the one
loud colour. Host-owned keys are not handled here.
"""

from __future__ import annotations

import os
import unicodedata
from typing import Any


NAME = "strip"
NERD = os.environ.get("DELEGATE_DASHBOARD_NERD") == "1"

# Nerd Codicons are 1-cell when the pane font is patched; fallbacks are
# always 1-cell. The Remaining bar is Unicode block elements, not Nerd.
_GLYPHS_NERD = {
    "pick": "\ued59",  # 
    "veto": "\uea78",  # 
    "unknown": "\ueb32",  # 
    "steal": "\ueaa1",  # 
    "carried": "\uea71",  # 
    "order_p": "\ueb06",  # 
    "order_g": "\ueb01",  # 
    "folded": "\ueab6",  # 
    "open": "\ueab4",  # 
}
_GLYPHS_PLAIN = {
    "pick": "*",
    "veto": "!",
    "unknown": "?",
    "steal": "^",
    "carried": "·",
    "order_p": "P",
    "order_g": "G",
    "folded": ">",
    "open": "v",
}

RAIL = "▌"
RAIL_PLAIN = ">"
BAR_FULL = "█"
BAR_HALF = "▌"
BAR_EIGHTH = "▏"
BAR_EMPTY = "·"
EMDASH = "—"
TIMES = "×"
GE = "≥"

DARK = {
    "ink": "#12141a",
    "fg": "#d6d3c8",
    "mute": "#7a7e6e",
    "pick": "#e6b84d",
    "veto": "#c45c4a",
    "steal": "#6db3a8",
    "selbg": "#2c3340",
}
LIGHT = {
    "ink": "#f3efe4",
    "fg": "#2a2e28",
    "mute": "#6e7268",
    "pick": "#9a6b12",
    "veto": "#a33b32",
    "steal": "#1f6f68",
    "selbg": "#d9e0d2",
}

# Forced 1-cell: Codicons plus the bar/rail marks the grid depends on.
_ONE_CELL = frozenset(
    list(_GLYPHS_NERD.values())
    + list(_GLYPHS_PLAIN.values())
    + [RAIL, RAIL_PLAIN, BAR_FULL, BAR_HALF, BAR_EIGHTH, BAR_EMPTY, EMDASH, TIMES, GE]
)

RESET = "\033[0m"

# Drop first: reason, meter, pace, bar, rem. Never drop st/ord/src/lane.
_DROP_REASON = 0
_DROP_METER = 1
_DROP_PACE = 2
_DROP_BAR = 3
_DROP_REM = 4


def _glyphs() -> dict[str, str]:
    return _GLYPHS_NERD if NERD else _GLYPHS_PLAIN


def _palette() -> dict[str, str]:
    spec = os.environ.get("COLORFGBG", "")
    bg = spec.split(";")[-1] if spec else ""
    if bg in {"7", "15"}:
        return LIGHT
    return DARK


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.removeprefix("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _cell_width(ch: str) -> int:
    if not ch or unicodedata.combining(ch):
        return 0
    if ch in _ONE_CELL:
        return 1
    code = ord(ch)
    if code == 0 or unicodedata.category(ch) in {"Cc", "Cf"}:
        return 0
    width = unicodedata.east_asian_width(ch)
    if width in {"W", "F"}:
        return 2
    return 1


def cells(text: str) -> int:
    """Visible terminal cells, not Python characters."""
    return sum(_cell_width(ch) for ch in text)


def fit(text: str, width: int, align: str = "left") -> str:
    """Clip to `width` cells and pad to that width."""
    if width <= 0:
        return ""
    out: list[str] = []
    used = 0
    for ch in text:
        w = _cell_width(ch)
        if used + w > width:
            break
        out.append(ch)
        used += w
    pad = width - used
    body = "".join(out)
    if pad <= 0:
        return body
    if align == "right":
        return (" " * pad) + body
    return body + (" " * pad)


def _sgr(*, fg: str | None = None, bg: str | None = None, bold: bool = False) -> str:
    parts = ["0"]
    if bold:
        parts.append("1")
    if fg:
        r, g, b = _rgb(fg)
        parts.append(f"38;2;{r};{g};{b}")
    if bg:
        r, g, b = _rgb(bg)
        parts.append(f"48;2;{r};{g};{b}")
    return "\033[" + ";".join(parts) + "m"


def _paint(
    segments: list[tuple[str, str | None, bool]],
    width: int,
    *,
    bg: str,
    default_fg: str,
) -> str:
    parts: list[str] = []
    used = 0
    for text, fg, bold in segments:
        if used >= width:
            break
        w = cells(text)
        if used + w > width:
            text = fit(text, width - used)
            w = cells(text)
        if not text:
            continue
        parts.append(_sgr(fg=fg or default_fg, bg=bg, bold=bold) + text)
        used += w
    if used < width:
        parts.append(_sgr(fg=default_fg, bg=bg) + (" " * (width - used)))
    parts.append(RESET)
    return "".join(parts)


def _percent(value: Any) -> str:
    if value is None:
        return EMDASH
    return f"{round(float(value) * 100):g}%"


def _pace(value: Any) -> str:
    if value is None:
        return EMDASH
    return f"{float(value):.2f}{TIMES}"


def _bar(remaining: Any) -> str:
    if remaining is None:
        return BAR_EMPTY * 8
    try:
        fill = max(0.0, min(1.0, float(remaining))) * 8.0
    except (TypeError, ValueError):
        return BAR_EMPTY * 8
    full = int(fill)
    frac = fill - full
    out: list[str] = []
    for i in range(8):
        if i < full:
            out.append(BAR_FULL)
        elif i == full:
            if frac >= 0.25:
                out.append(BAR_HALF)
            elif frac > 0 or (full == 0 and fill > 0):
                out.append(BAR_EIGHTH)
            else:
                out.append(BAR_EMPTY)
        else:
            out.append(BAR_EMPTY)
    return "".join(out)


def _short_reason(row: dict[str, Any], state: dict[str, Any]) -> str:
    reason = str(row.get("reason") or "")
    if reason == "pick":
        return "Pick"
    if reason.startswith("stolen by pace:"):
        rest = reason.split(":", 1)[1].strip()
        parts = rest.replace(">=", " ").replace("+", " ").split()
        nums: list[str] = []
        for part in parts:
            try:
                nums.append(f"{float(part):.2f}")
            except ValueError:
                continue
        if len(nums) >= 3:
            return f"steal {nums[0]}{GE}{nums[1]}+{nums[2]}"
        return "steal"
    if reason.startswith("vetoed:gate"):
        gate = (state.get("policy") or {}).get("gate") or {}
        gate_txt = gate.get("display") or _percent(gate.get("value"))
        return f"Gate {_percent(row.get('remaining'))}<{gate_txt}"
    if reason.startswith("unknown meter"):
        return "unknown Meter"
    if reason.startswith("vetoed:cli"):
        return "CLI"
    if reason.startswith("vetoed:floor"):
        return "floor"
    if reason.startswith("vetoed:ceiling"):
        return "ceiling"
    if reason == "eligible":
        return ""
    return reason


def _status_glyph(row: dict[str, Any], glyphs: dict[str, str]) -> tuple[str, str]:
    """Lane-row mark and its colour role: pick, veto, unknown, steal, carried."""
    pal = _palette()
    reason = str(row.get("reason") or "")
    if reason == "pick":
        return glyphs["pick"], pal["pick"]
    if reason.startswith("vetoed:gate"):
        return glyphs["veto"], pal["veto"]
    if reason.startswith("unknown meter") or row.get("remaining") is None:
        return glyphs["unknown"], pal["mute"]
    if reason.startswith("stolen by pace:"):
        return glyphs["steal"], pal["steal"]
    return glyphs["carried"], pal["mute"]


def _order_src(row: dict[str, Any], state: dict[str, Any], glyphs: dict[str, str]) -> str:
    source = row.get("order_source")
    policy = (state.get("project") or {}).get("policy")
    if not source:
        return "?"
    if source == policy:
        return glyphs["order_p"]
    return glyphs["order_g"]


def _meters_on(state: dict[str, Any]) -> bool:
    meters = (state.get("policy") or {}).get("meters") or {}
    return meters.get("value", True) is not False


def _visible_rows(
    state: dict[str, Any], view: dict[str, Any]
) -> list[tuple[str, dict[str, Any] | None]]:
    """Body entries: ('tier', tier_dict) or ('lane', row_with_tier)."""
    folded = set(view.get("folded") or [])
    eligible_only = bool(view.get("eligible_only"))
    entries: list[tuple[str, dict[str, Any] | None]] = []
    for tier in state.get("tiers") or []:
        number = tier.get("tier")
        entries.append(("tier", tier))
        if number in folded:
            continue
        for row in tier.get("rows") or []:
            if eligible_only and not row.get("eligible"):
                continue
            packed = dict(row)
            packed["_tier"] = number
            packed["_leader"] = tier.get("leader")
            entries.append(("lane", packed))
    return entries


def _drop_levels(width: int) -> set[int]:
    """Which droppable groups are hidden at this width."""
    hidden: set[int] = set()
    # rail sp st sp ord2 src sp lane20 sp meter14 sp rem5 sp bar8 sp pace6
    # sp reason. Prefix including the reason separator is 66.
    need = 66
    if width < need:
        hidden.add(_DROP_REASON)
        need -= 1  # reason separator; reason itself is flex
    if width < need:
        hidden.add(_DROP_METER)
        need -= 15
    if width < need:
        hidden.add(_DROP_PACE)
        need -= 7
    if width < need:
        hidden.add(_DROP_BAR)
        need -= 9
    if width < need:
        hidden.add(_DROP_REM)
        need -= 6
    return hidden


def _lane_width(width: int, hidden: set[int]) -> int:
    used = 8  # rail sp st sp ord2 src sp
    if _DROP_METER not in hidden:
        used += 15
    if _DROP_REM not in hidden:
        used += 6
    if _DROP_BAR not in hidden:
        used += 9
    if _DROP_PACE not in hidden:
        used += 7
    if _DROP_REASON not in hidden:
        used += 1
    remaining = width - used
    return max(1, min(20, remaining))


def _reason_width(width: int, hidden: set[int], lane_w: int) -> int:
    if _DROP_REASON in hidden:
        return 0
    used = 8 + lane_w
    if _DROP_METER not in hidden:
        used += 15
    if _DROP_REM not in hidden:
        used += 6
    if _DROP_BAR not in hidden:
        used += 9
    if _DROP_PACE not in hidden:
        used += 7
    used += 1  # space before reason
    return max(0, width - used)


def _lane_segments(
    row: dict[str, Any],
    state: dict[str, Any],
    *,
    selected: bool,
    width: int,
) -> list[tuple[str, str | None, bool]]:
    pal = _palette()
    glyphs = _glyphs()
    hidden = _drop_levels(width)
    lane_w = _lane_width(width, hidden)
    reason_w = _reason_width(width, hidden, lane_w)
    mark, mark_fg = _status_glyph(row, glyphs)
    reason = _short_reason(row, state)
    is_pick = str(row.get("reason") or "") == "pick"
    is_veto = str(row.get("reason") or "").startswith("vetoed:gate")
    is_steal = str(row.get("reason") or "").startswith("stolen by pace:")
    meters_on = _meters_on(state)
    order = row.get("order")
    ord_txt = f"{order:d}" if isinstance(order, int) else EMDASH
    rem_txt = _percent(row.get("remaining"))
    pace_txt = _pace(row.get("pace"))
    rail = RAIL if selected else " "
    lane_fg = pal["pick"] if is_pick else pal["fg"]
    rem_fg = pal["veto"] if is_veto else pal["fg"]
    pace_fg = pal["mute"] if not meters_on else (pal["steal"] if is_steal else pal["fg"])
    reason_fg = pal["pick"] if is_pick else (
        pal["veto"] if is_veto else (pal["steal"] if is_steal else pal["mute"])
    )
    segs: list[tuple[str, str | None, bool]] = [
        (fit(rail, 1), pal["fg"], selected),
        (" ", pal["fg"], False),
        (fit(mark, 1), mark_fg, is_pick),
        (" ", pal["fg"], False),
        (fit(ord_txt, 2, "right"), pal["mute"], False),
        (fit(_order_src(row, state, glyphs), 1), pal["mute"], False),
        (" ", pal["fg"], False),
        (fit(str(row.get("lane") or ""), lane_w), lane_fg, is_pick),
    ]
    if _DROP_METER not in hidden:
        segs.append((" ", pal["fg"], False))
        segs.append((fit(str(row.get("meter") or ""), 14), pal["mute"], False))
    if _DROP_REM not in hidden:
        segs.append((" ", pal["fg"], False))
        segs.append((fit(rem_txt, 5, "right"), rem_fg, False))
    if _DROP_BAR not in hidden:
        segs.append((" ", pal["fg"], False))
        segs.append((fit(_bar(row.get("remaining")), 8), rem_fg, False))
    if _DROP_PACE not in hidden:
        segs.append((" ", pal["fg"], False))
        segs.append((fit(pace_txt, 6, "right"), pace_fg, False))
    if _DROP_REASON not in hidden and reason_w:
        segs.append((" ", pal["fg"], False))
        segs.append((fit(reason, reason_w), reason_fg, is_pick))
    return segs


def _header_identity(state: dict[str, Any], width: int) -> list[tuple[str, str | None, bool]]:
    pal = _palette()
    mute = pal["mute"]
    fg = pal["fg"]
    project = str((state.get("project") or {}).get("name") or "")
    policy = state.get("policy") or {}
    gate = (policy.get("gate") or {}).get("display") or ""
    margin = (policy.get("margin") or {}).get("display") or ""
    meters = policy.get("meters") or {}
    meters_txt = meters.get("display") or ("on" if meters.get("value", True) else "off")
    usage = str((state.get("usage") or {}).get("status") or "")
    if width >= 90:
        left = fit(project, min(cells(project), max(8, width // 3)))
        mid = f"Gate {gate}  Margin {margin}  Meters {meters_txt}  usage {usage}"
        right = "?"
        gap = width - cells(left) - cells(mid) - cells(right)
        if gap < 2:
            mid = f"Gate {gate}  Margin {margin}  Meters {meters_txt}"
            gap = width - cells(left) - cells(mid) - cells(right)
        if gap < 2:
            mid = f"G{gate} M{margin}"
            gap = max(1, width - cells(left) - cells(mid) - cells(right))
        return [
            (left, fg, False),
            (" " * max(1, gap - 1), mute, False),
            (mid, mute, False),
            (" ", mute, False),
            (right, mute, False),
        ]
    compact = f"G{gate} M{margin}"
    name_w = max(0, width - cells(compact) - 1)
    return [
        (fit(project, name_w), fg, False),
        (" ", mute, False),
        (fit(compact, min(cells(compact), width)), mute, False),
    ]


def _header_leaders(state: dict[str, Any], width: int) -> list[tuple[str, str | None, bool]]:
    pal = _palette()
    glyphs = _glyphs()
    mute = pal["mute"]
    pick = pal["pick"]
    wide = width >= 80
    chunks: list[tuple[str, str | None, bool]] = []
    tiers = list(state.get("tiers") or [])
    if not tiers:
        return [(fit("", width), mute, False)]
    # First-pass labels; then clip leaders until the strip fits.
    leaders = []
    for tier in tiers:
        name = tier.get("leader")
        leaders.append((tier.get("tier"), name))

    def labels(trim: int | None) -> list[tuple[str, bool]]:
        out = []
        for number, name in leaders:
            if name:
                shown = name if trim is None else name[:trim]
                if wide:
                    text = f"T{number} {glyphs['pick']} {shown}"
                else:
                    text = f"T{number}{glyphs['pick']}{shown}"
                out.append((text, True))
            else:
                text = f"T{number} {EMDASH}" if wide else f"T{number}{EMDASH}"
                out.append((text, False))
        return out

    sep = "     " if wide else " "
    chosen = labels(None)
    for trim in (None, 20, 14, 10, 8, 6, 4, 2):
        chosen = labels(trim)
        joined = sep.join(text for text, _ in chosen)
        if cells(joined) <= width:
            break
    parts: list[tuple[str, str | None, bool]] = []
    used = 0
    for i, (text, is_leader) in enumerate(chosen):
        if i:
            if used + cells(sep) > width:
                break
            parts.append((sep, mute, False))
            used += cells(sep)
        clipped = text if used + cells(text) <= width else fit(text, width - used)
        parts.append((clipped, pick if is_leader else mute, False))
        used += cells(clipped)
        if used >= width:
            break
    chunks.extend(parts)
    return chunks


def _tier_header(
    tier: dict[str, Any], view: dict[str, Any], width: int
) -> list[tuple[str, str | None, bool]]:
    pal = _palette()
    glyphs = _glyphs()
    folded = set(view.get("folded") or [])
    number = tier.get("tier")
    mark = glyphs["folded"] if number in folded else glyphs["open"]
    leader = tier.get("leader")
    if leader:
        body = f"{mark} T{number} {glyphs['pick']} {leader}"
        fg = pal["pick"]
    else:
        body = f"{mark} T{number} {EMDASH}"
        fg = pal["mute"]
    return [(fit(body, width), fg, False)]


def _footer_text(
    *,
    editor: Any,
    message: str,
    state: dict[str, Any],
    view: dict[str, Any],
    width: int,
) -> list[tuple[str, str | None, bool]]:
    pal = _palette()
    if editor is not None:
        field = str(getattr(editor, "field", "") or "gate")
        text = str(getattr(editor, "text", "") or "")
        label = "Gate" if field == "gate" else "Margin" if field == "margin" else field
        unit = "" if text.endswith("%") else "%"
        body = f"{label} {text}{unit}_  Enter/Esc"
        return [(fit(body, width), pal["fg"], True)]
    if message:
        return [(fit(message, width), pal["fg"], False)]
    save = state.get("save") or {}
    if save.get("status") not in (None, "idle") and save.get("detail"):
        fg = pal["pick"] if save.get("status") == "saved" else pal["veto"]
        return [(fit(str(save["detail"]), width), fg, save.get("status") != "saved")]
    if state.get("error"):
        return [(fit(str(state["error"]), width), pal["veto"], True)]
    filt = " elig" if view.get("eligible_only") else ""
    body = f"j/k sel  J/K move  [] Tier  f elig  c fold  ? help  layout: {NAME} (v next){filt}"
    return [(fit(body, width), pal["mute"], False)]


def _help_lines(width: int, height: int) -> list[str]:
    pal = _palette()
    bg = pal["ink"]
    lines = [
        "strip  one Lane, one row",
        "0  first row    G  last row",
        "[  previous Tier    ]  next Tier",
        "f  eligible Lanes only",
        "c  fold the selected Lane's Tier",
        "?  close this overlay",
        "host: j/k select  J/K move  g/m edit  r reload  v variant  q",
    ]
    painted = [
        _paint([(fit(line, width), pal["fg"], i == 0)], width, bg=bg, default_fg=pal["fg"])
        for i, line in enumerate(lines)
    ]
    blank = _paint([], width, bg=bg, default_fg=pal["fg"])
    while len(painted) < height:
        painted.append(blank)
    return painted[:height]


def _follow_selection(
    view: dict[str, Any],
    entries: list[tuple[str, dict[str, Any] | None]],
    selected_lane: str | None,
    page: int,
) -> None:
    prior = view.get("_selected")
    if selected_lane != prior:
        view["follow"] = True
    view["_selected"] = selected_lane
    if page <= 0:
        view["offset"] = 0
        return
    selected_index = None
    if selected_lane:
        for i, (kind, payload) in enumerate(entries):
            if kind == "lane" and payload and payload.get("lane") == selected_lane:
                selected_index = i
                break
            if (
                kind == "tier"
                and payload
                and selected_index is None
                and any(
                    row.get("lane") == selected_lane for row in (payload.get("rows") or [])
                )
                and payload.get("tier") in set(view.get("folded") or [])
            ):
                selected_index = i
    max_off = max(0, len(entries) - page)
    offset = int(view.get("offset") or 0)
    if view.get("follow", True) and selected_index is not None:
        if selected_index < offset:
            offset = selected_index
        elif selected_index >= offset + page:
            offset = selected_index - page + 1
    view["offset"] = max(0, min(offset, max_off))


def render(
    state: dict[str, Any],
    *,
    width: int,
    height: int,
    selected_lane: str | None,
    editor: Any,
    message: str,
    view: dict[str, Any],
) -> list[str]:
    """Return exactly `height` ANSI strings, each at most `width` cells."""
    if not isinstance(view, dict):
        view = {}
    width = max(0, int(width))
    height = max(0, int(height))
    pal = _palette()
    bg = pal["ink"]
    selbg = pal["selbg"]
    if height == 0:
        return []

    footer = _paint(
        _footer_text(
            editor=editor, message=message or "", state=state, view=view, width=width
        ),
        width,
        bg=bg,
        default_fg=pal["mute"],
    )
    if height == 1:
        return [footer]

    identity = _paint(
        _header_identity(state, width), width, bg=bg, default_fg=pal["fg"]
    )
    if height == 2:
        return [identity, footer]

    leaders = _paint(
        _header_leaders(state, width), width, bg=bg, default_fg=pal["mute"]
    )
    chrome = 3  # identity, leaders, footer
    body_h = height - chrome
    if view.get("help"):
        body = _help_lines(width, body_h)
        return [identity, leaders, *body, footer]

    entries = _visible_rows(state, view)
    view["_body_len"] = len(entries)
    view["_tier_starts"] = [
        i for i, (kind, _) in enumerate(entries) if kind == "tier"
    ]
    _follow_selection(view, entries, selected_lane, body_h)
    offset = int(view.get("offset") or 0)
    window = entries[offset : offset + body_h]
    blank = _paint([], width, bg=bg, default_fg=pal["fg"])
    body: list[str] = []
    for kind, payload in window:
        if kind == "tier" and payload is not None:
            body.append(
                _paint(_tier_header(payload, view, width), width, bg=bg, default_fg=pal["mute"])
            )
            continue
        if kind == "lane" and payload is not None:
            selected = payload.get("lane") == selected_lane
            row_bg = selbg if selected else bg
            body.append(
                _paint(
                    _lane_segments(payload, state, selected=selected, width=width),
                    width,
                    bg=row_bg,
                    default_fg=pal["fg"],
                )
            )
            continue
        body.append(blank)
    while len(body) < body_h:
        body.append(blank)
    return [identity, leaders, *body[:body_h], footer]


def handle_key(key: str, state: dict[str, Any], view: dict[str, Any]) -> bool:
    """Consume variant keys. Return True when the key is used."""
    if not isinstance(view, dict):
        return False
    if key == "?":
        view["help"] = not bool(view.get("help"))
        return True
    if key == "f":
        view["eligible_only"] = not bool(view.get("eligible_only"))
        view["follow"] = True
        return True
    if key == "c":
        lane = view.get("_selected")
        tier_n = None
        for tier in state.get("tiers") or []:
            if any(row.get("lane") == lane for row in (tier.get("rows") or [])):
                tier_n = tier.get("tier")
                break
        if tier_n is None:
            return True
        folded = list(view.get("folded") or [])
        if tier_n in folded:
            folded = [item for item in folded if item != tier_n]
        else:
            folded.append(tier_n)
        view["folded"] = folded
        view["follow"] = True
        return True
    if key in ("0", "\x1b[H", "\x1b[1~", "\x1bOH"):
        view["offset"] = 0
        view["follow"] = False
        view["help"] = False
        return True
    if key in ("G", "\x1b[F", "\x1b[4~", "\x1bOF"):
        body_len = int(view.get("_body_len") or 0)
        view["offset"] = max(0, body_len)
        view["follow"] = False
        view["help"] = False
        return True
    if key in ("[", "]"):
        starts = list(view.get("_tier_starts") or [])
        offset = int(view.get("offset") or 0)
        if not starts:
            return True
        if key == "]":
            nxt = [item for item in starts if item > offset]
            view["offset"] = nxt[0] if nxt else starts[-1]
        else:
            prev = [item for item in starts if item < offset]
            view["offset"] = prev[-1] if prev else starts[0]
        view["follow"] = False
        view["help"] = False
        return True
    return False
