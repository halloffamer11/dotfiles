#!/usr/bin/env python3
"""PROTOTYPE: the shipped dashboard rendering, behind the variant contract.

Throwaway.  The header, body and footer are the ones ``dashboard.py`` drew
before the layout seam landed and are not changed here.  Only the seam moved:
the selected body line is found by row index instead of by matching ``"| >"``
text, the scroll offset lives in the host-supplied ``view``, and the footer
names the layout.

Standard library only.
"""

from __future__ import annotations

import os


NAME = "current"

RESET = "\033[0m"
MUTED = "#8d8d89"
FOREGROUND = "#e7e7e7"
ERROR = "#d76563"
SUCCESS = "#78bd74"
METERS_OFF_EFFECT = "Gate, Margin and Pace inactive; Remaining is cached"


def foreground(hex_color: str) -> str:
    value = hex_color.removeprefix("#")
    return f"\033[38;2;{int(value[0:2], 16)};{int(value[2:4], 16)};{int(value[4:6], 16)}m"


def paint(text: str, color: str = FOREGROUND, *, bold: bool = False, width: int) -> str:
    text = text[: max(0, width)]
    weight = "\033[1m" if bold else ""
    return f"{weight}{foreground(color)}{text}{RESET}"


def paint_line(line, width: int) -> str:
    """Paint one compose line; an optional 4th item is mixed-color segments."""
    text, color, bold = line[0], line[1], line[2]
    parts = line[3] if len(line) > 3 else None
    if not parts:
        return paint(text, color, bold=bold, width=width)
    remaining = max(0, width)
    painted = []
    for part_text, part_color, part_bold in parts:
        if remaining <= 0:
            break
        painted.append(paint(part_text, part_color, bold=part_bold, width=remaining))
        remaining -= min(len(part_text), remaining)
    return "".join(painted)


def percent(value):
    return "—" if value is None else f"{round(value * 100):g}%"


def pace(value):
    return "—" if value is None else f"{value:.2f}×"


def source_label(source, state, *, empty="unknown"):
    if not source:
        return empty
    if source == state["project"]["policy"]:
        return "project:.delegate/routing.json"
    return f"global:{os.path.basename(source)}"


def meters_policy(state):
    """Read sourced metering state; `effect` may be absent until the model lands."""
    meters = (state.get("policy") or {}).get("meters") or {}
    value = meters.get("value", True)
    display = meters.get("display") or ("on" if value else "off")
    effect = meters.get("effect")
    if not effect and value is False:
        effect = METERS_OFF_EFFECT
    return {
        "value": value,
        "display": display,
        "source": meters.get("source"),
        "effect": effect or "",
    }


def order_label(row, state):
    """Effective Order with its catalog source, not a second sorting rule."""
    if row["order"] is None:
        return "—"
    source = row.get("order_source")
    mark = "?" if not source else "p" if source == state["project"]["policy"] else "g"
    return f"{row['order']}{mark}"


def body_lines(state, width, selected_lane=None):
    """Return semantic terminal lines and the selected Lane's line index."""
    meters_off = meters_policy(state)["value"] is False
    cached = " cached" if meters_off else ""
    lines = []
    selected_index = None
    for tier in state["tiers"]:
        color = tier["color"]
        leader = tier["leader"] or "none eligible"
        lines.append((f"┃ Tier {tier['tier']}   ◆ {leader}", color, True))
        if width >= 132:
            lines.append(
                (
                    "┃    Ord  Lane                     Model                Effort  "
                    "Harness  Meter             Rem   Pace   OK  Reason",
                    MUTED,
                    False,
                )
            )
        else:
            lines.append(("┃    Ord Lane · Model / Effort @ Harness · Meter", MUTED, False))
        if not tier["rows"]:
            lines.append(("┃    No carried lanes", MUTED, False))
        for row in tier["rows"]:
            leader_mark = "◆" if row["lane"] == tier["leader"] else "·"
            cursor_mark = ">" if row["lane"] == selected_lane else " "
            if row["lane"] == selected_lane:
                selected_index = len(lines)
            order = order_label(row, state)
            eligible = "yes" if row["eligible"] else "no"
            row_color = color if leader_mark == "◆" else FOREGROUND
            is_leader = leader_mark == "◆"
            rem_text = percent(row["remaining"])
            pace_text = pace(row["pace"])
            if width >= 132:
                left = (
                    f"┃ {cursor_mark}{leader_mark} {order:>3}  {row['lane']:<24} "
                    f"{row['model']:<20} {row['effort']:<7} {row['harness']:<8} "
                    f"{row['meter']:<17} {rem_text:>4}{cached}"
                )
                pace_col = f"  {pace_text:>6}"
                right = f"  {eligible:<3} {row['reason']}"
                text = left + pace_col + right
                if meters_off:
                    lines.append(
                        (
                            text,
                            row_color,
                            is_leader,
                            (
                                (left, row_color, is_leader),
                                (pace_col, MUTED, False),
                                (right, row_color, is_leader),
                            ),
                        )
                    )
                else:
                    lines.append((text, row_color, is_leader))
            else:
                lines.append(
                    (
                        f"┃ {cursor_mark}{leader_mark} {order:>3} {row['lane']} · {row['model']} / "
                        f"{row['effort']} @ {row['harness']} · Meter {row['meter']}",
                        row_color,
                        is_leader,
                    )
                )
                prefix = f"┃       Remaining {rem_text}{cached}"
                pace_part = f" · Pace {pace_text}"
                suffix = f" · eligible {eligible} · {row['reason']}"
                text = prefix + pace_part + suffix
                if meters_off:
                    lines.append(
                        (
                            text,
                            row_color,
                            is_leader,
                            (
                                (prefix, row_color, is_leader),
                                (pace_part, MUTED, False),
                                (suffix, row_color, is_leader),
                            ),
                        )
                    )
                else:
                    lines.append((text, row_color, is_leader))
        lines.append(("", FOREGROUND, False))
    return lines, selected_index


def compose(
    state,
    offset,
    width,
    height,
    selected_lane=None,
    *,
    follow_selection=True,
    editor=None,
    message="",
):
    """Compose a clipped viewport with persistent project identity and key help."""
    footer_keys = (
        "jk/↑↓ select · JK/⇧↑↓ move · g Gate · m Margin · r reload · q close"
    )
    gate = state["policy"]["gate"]
    margin = state["policy"]["margin"]
    meters = meters_policy(state)
    inactive = " inactive" if meters["value"] is False else ""
    project = state["project"]
    usage = state["usage"]
    header = [
        (f"Pinned project  {project['name']}  {project['root']}", FOREGROUND, True),
        ("Delegate project routing  /  prototype", FOREGROUND, True),
        ("Ord: p=project · g=global/fallback (derived from global Order/name)", MUTED, False),
    ]
    policy_text = (
        f"Gate {gate['display']} [{source_label(gate['source'], state)}]{inactive}   "
        f"Margin {margin['display']} [{source_label(margin['source'], state)}]{inactive}"
    )
    meters_text = (
        f"Meters {meters['display']} [{source_label(meters['source'], state, empty='default')}]"
    )
    # A narrow pane must not clip the Meters source off the end of the policy line.
    if len(policy_text) + 3 + len(meters_text) <= width:
        header.append((f"{policy_text}   {meters_text}", MUTED, False))
    else:
        header.append((policy_text, MUTED, False))
        header.append((meters_text, MUTED, False))
    if meters["value"] is False:
        header.append((meters["effect"], MUTED, False))
    header.append(
        (
            f"{usage['label']} · cached, display-only · {usage['status']} · {usage['path']}",
            MUTED if usage["status"] == "ok" else ERROR,
            False,
        )
    )
    if usage.get("detail"):
        header.append((usage["detail"], ERROR, False))
    if state.get("error"):
        header.append((state["error"], ERROR, True))
    if editor is not None:
        header.append(
            (
                f"Edit {editor.field.title()} percentage (0–100): {editor.text}_  "
                "Enter save · Esc cancel",
                FOREGROUND,
                True,
            )
        )
    save = state.get("save", {})
    if save.get("status") != "idle" and save.get("detail"):
        color = SUCCESS if save["status"] == "saved" else ERROR
        header.append((save["detail"], color, save["status"] != "saved"))
    if message:
        header.append((message, MUTED, False))

    footer_height = 1
    layout_tag = f" · layout: {NAME} (v next)"
    if height <= footer_height:
        return [(footer_keys + layout_tag, MUTED, False)], 0, 0
    if height == 2:
        return [header[0], (footer_keys + layout_tag, MUTED, False)], 0, 0

    max_header = max(1, height - footer_height - 1)
    header = header[:max_header]
    available = max(1, height - len(header) - footer_height)
    body, selected_line = body_lines(state, width, selected_lane)
    max_offset = max(0, len(body) - available)
    offset = min(max(0, offset), max_offset)
    if follow_selection and selected_line is not None:
        if selected_line < offset:
            offset = selected_line
        elif selected_line >= offset + available:
            offset = selected_line - available + 1
    visible = body[offset : offset + available]
    extent = "all" if not body else f"{offset + 1}–{min(len(body), offset + available)}/{len(body)}"
    footer_text = (
        f"editing {editor.field.title()} · type value · Enter save · Esc cancel [{extent}]"
        if editor is not None
        else f"{footer_keys} [{extent}]"
    ) + layout_tag
    footer = [(footer_text, MUTED, False)]
    return header + visible + footer, offset, len(body)


def render(state, *, width, height, selected_lane, editor, message, view):
    """Return exactly `height` painted strings for this frame."""
    follow = view.get("last_selected", object()) != selected_lane
    lines, offset, total = compose(
        state,
        view.get("offset", 0),
        width,
        height,
        selected_lane,
        follow_selection=follow,
        editor=editor,
        message=message,
    )
    view["offset"] = offset
    view["total"] = total
    view["last_selected"] = selected_lane
    rendered = [paint_line(line, width) for line in lines]
    rendered.extend([""] * max(0, height - len(rendered)))
    return rendered[:height]


def handle_key(key, state, view):
    """Scroll keys this layout owns; the host keeps selection and the editors."""
    if key in ("\x1b[6~", " "):
        view["offset"] = view.get("offset", 0) + 8
    elif key == "\x1b[5~":
        view["offset"] = max(0, view.get("offset", 0) - 8)
    elif key == "G":
        view["offset"] = max(0, view.get("total", 1) - 1)
    else:
        return False
    # The selected Lane is unchanged, so the next frame does not follow it back.
    return True
