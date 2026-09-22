#!/usr/bin/env python3
"""effort.py — scrape-then-convert pipeline for per-effort benchmark data.

Three stages, one trust boundary:

    HTML  --[1 pack: deterministic]-->  packet.txt
    packet.txt  --[2 extract: LLM]-->  rows.json
    rows.json + packet.txt  --[3 check: deterministic]-->  accepted.json / rejected.json

An LLM may select and restructure text. It may not originate a number.
Stage 3 enforces that mechanically.

A row keeps the model name its source printed — `GPT-6 Astra` from
Terminal-Bench, `gpt-5.6-luna` from SWE Refactor Bench. Normalising that to a
catalog slug here would be originating an identifier out of local knowledge the
packet cannot vouch for, which is the same objection as originating a number, so
the reconciliation happens where that knowledge lives: `catalog.py`'s
`resolve_published_model` and the lane field `published_as`, read by whoever
consumes the rows (ticket 16).

Stage 3 catches invented distinctive numbers and cannot vouch for small
integers, so a human still reads accepted.json. A badge that sits in different
markup from its row will degrade to a rejection rather than a false accept:
a missed badge is recoverable, a false verified is not.

One source skips stage 2. Artificial Analysis embeds its whole dataset as JSON
in every /models/<slug> page, so `aa` reads the rows straight out of that
payload and writes the payload itself as the packet; `check` then runs as it
does for any other source. `extract` refuses an Artificial Analysis packet.

Default extract lane is flash-high@agy; terra-high@codex is the fallback
for packets that lane handles badly.

agy passes the prompt as a CLI argument, which Linux caps at ~128KB
(MAX_ARG_STRLEN = 131,072 bytes). The dispatch harness and brief wrapper add
~3.5KB of prompt overhead (preamble + leash ~590B, return schema ~1,370B,
working directory/clause ~300B, and extract instructions ~1,275B). To keep
the total prompt within OS limits with comfortable headroom (~25KB), packets
larger than the chunk budget (default 100KB = 102,400 bytes) are split on
table or row boundaries into self-contained chunks that each carry the full
packet provenance header (## source, ## url, ## title, ## sha256, ## packed).
Each chunk is extracted independently, and rows are combined and de-duplicated
on (source, model, effort, benchmark) before check validates them against the
whole original packet.

CLI forms:
  effort.py pack <html-file> --source <id> [--url <url>] [-o <out>]
  effort.py extract --packet <file> --out-dir <dir> [--lane <lane>] [--budget <bytes>]
  effort.py check --rows <rows.json> --packet <file> [--out-dir <dir>]
  effort.py run <html-file> --source <id> --out-dir <dir> [--url <url>] [--lane <lane>] [--budget <bytes>]
  effort.py aa --out-dir <dir> [--url <url>] [--html <file>]
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

DEFAULT_LANE = "flash-high@agy"
FALLBACK_LANE = "terra-high@codex"
DEFAULT_BUDGET = 100 * 1024  # 100KB in bytes; prompt overhead is ~3.5KB, fitting within Linux ~128KB arg cap
ROW_IDENTITY_FIELDS = ("source", "model", "effort", "benchmark")
EFFORT_VALUES = (
    "none", "low", "medium", "high", "xhigh", "max", "ultra", "unspecified",
)
# The words a page may print for an effort, where the row's word is not one of
# them: Artificial Analysis prints `Non-reasoning` for the API's `none`.
EFFORT_PRINTED = {"none": ("none", "non-reasoning")}
PROVENANCE_VALUES = ("verified", "self-reported", "unlabelled")
PROVENANCE_STEMS = {
    "verified": ("verif", "official"),
    "self-reported": ("self-report", "submitt", "communit"),
}
NUMERIC_FIELDS = ("score", "cost_usd", "tokens")
CLIENT_RENDERED_MSG = "no static tabular data; page is likely client-rendered"
SR_CLASSES = frozenset({"sr-only", "visually-hidden", "screen-reader-text"})
VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})


def is_qualifying_label(text):
    """Check if label has >= 4 characters and contains at least one digit."""
    if len(text) < 4:
        return False
    return any(ch.isdigit() for ch in text)


# Number-like tokens as they appear on a packed page: $1,234.50, 19, 19.0, 72.5%.
NUM_TOKEN = re.compile(
    r"\$?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
)

ROW_SCHEMA = (
    '{"source": str, "url": str|null, "model": str, "effort": str,\n'
    ' "benchmark": str, "score": number|null, "score_unit": str|null,\n'
    ' "cost_usd": number|null, "tokens": number|null,\n'
    ' "observed": "YYYY-MM-DD",\n'
    ' "provenance": "verified" | "self-reported" | "unlabelled",\n'
    ' "uncertain": bool}'
)


class EffortError(Exception):
    """Plain-language effort pipeline error."""


class ClientRenderedError(EffortError):
    """No static table or JSON-LD survived packing; exit 2."""


def utc_today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def format_json(doc):
    """Canonical JSON text: indent 2, UTF-8, trailing newline."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def collapse_ws(text):
    return " ".join(text.split())


def _attr(attrs, name):
    for key, value in attrs:
        if key == name:
            return value or ""
    return ""


def _is_jsonld(attrs):
    t = _attr(attrs, "type").strip().lower()
    return t == "application/ld+json" or t.startswith("application/ld+json;")


class PacketParser(HTMLParser):
    """Collect tables, labels, JSON-LD, embedded scripts, and title; drop style/svg/noscript."""

    SKIP = frozenset({"style", "svg", "noscript"})
    CELL_TAGS = frozenset({"td", "th"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_chunks = []
        self.in_title = 0
        self.skip_depth = 0
        self.jsonld_chunks = None
        self.jsonld_blocks = []
        self.script_chunks = None
        self.script_attrs = None
        self.script_blocks = []
        self.tables = []
        self.table_stack = []
        self.sr_stack = []
        self.seen_labels = set()
        self.labels = []

    def _maybe_add_label(self, text):
        if is_qualifying_label(text) and text not in self.seen_labels:
            self.seen_labels.add(text)
            self.labels.append(text)

    def handle_starttag(self, tag, attrs):
        if self.jsonld_chunks is not None or self.script_chunks is not None:
            return
        if tag == "script":
            if _is_jsonld(attrs):
                self.jsonld_chunks = []
            else:
                self.script_chunks = []
                self.script_attrs = attrs
            return
        if tag in self.SKIP:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title += 1
            return

        for name, val in attrs:
            if name.lower() in ("title", "aria-label") and val:
                self._maybe_add_label(collapse_ws(val))

        classes = set()
        for name, val in attrs:
            if name.lower() == "class" and val:
                classes = {c.lower() for c in val.split()}
                break
        is_sr = tag not in VOID_TAGS and bool(classes & SR_CLASSES)

        if self.sr_stack:
            for item in self.sr_stack:
                if item["tag"] == tag:
                    item["depth"] += 1

        if is_sr:
            self.sr_stack.append({"tag": tag, "depth": 0, "chunks": []})

        if tag == "table":
            self.table_stack.append({"rows": [], "row": None, "cell": None})
            return
        if not self.table_stack:
            return
        top = self.table_stack[-1]
        if tag == "tr":
            self._finish_cell(top)
            self._finish_row(top)
            top["row"] = []
            return
        if tag in self.CELL_TAGS:
            self._finish_cell(top)
            if top["row"] is None:
                top["row"] = []
            top["cell"] = []

    def handle_endtag(self, tag):
        if tag == "script":
            if self.jsonld_chunks is not None:
                self.jsonld_blocks.append("".join(self.jsonld_chunks))
                self.jsonld_chunks = None
                return
            if self.script_chunks is not None:
                self.script_blocks.append((self.script_attrs or [], "".join(self.script_chunks)))
                self.script_chunks = None
                self.script_attrs = None
                return
        if self.jsonld_chunks is not None or self.script_chunks is not None:
            return
        if tag in self.SKIP:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "title" and self.in_title:
            self.in_title -= 1
            return

        if self.sr_stack:
            top = self.sr_stack[-1]
            if top["tag"] == tag and top["depth"] == 0:
                finished = self.sr_stack.pop()
                self._maybe_add_label(collapse_ws("".join(finished["chunks"])))
                for item in self.sr_stack:
                    if item["tag"] == tag and item["depth"] > 0:
                        item["depth"] -= 1
            else:
                for item in self.sr_stack:
                    if item["tag"] == tag and item["depth"] > 0:
                        item["depth"] -= 1

        if not self.table_stack:
            return
        top = self.table_stack[-1]
        if tag in self.CELL_TAGS:
            self._finish_cell(top)
            return
        if tag == "tr":
            self._finish_cell(top)
            self._finish_row(top)
            return
        if tag == "table":
            self._finish_cell(top)
            self._finish_row(top)
            finished = self.table_stack.pop()
            if len(finished["rows"]) >= 2:
                self.tables.append(finished["rows"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self.jsonld_chunks is not None:
            self.jsonld_chunks.append(data)
            return
        if self.script_chunks is not None:
            self.script_chunks.append(data)
            return
        if self.skip_depth:
            return
        if self.in_title:
            self.title_chunks.append(data)
            return
        if self.sr_stack:
            for item in self.sr_stack:
                item["chunks"].append(data)
        if self.table_stack:
            top = self.table_stack[-1]
            if top["cell"] is not None:
                top["cell"].append(data)

    def close(self):
        super().close()
        if self.jsonld_chunks is not None:
            self.jsonld_blocks.append("".join(self.jsonld_chunks))
            self.jsonld_chunks = None
        if self.script_chunks is not None:
            self.script_blocks.append((self.script_attrs or [], "".join(self.script_chunks)))
            self.script_chunks = None
            self.script_attrs = None
        while self.sr_stack:
            finished = self.sr_stack.pop()
            self._maybe_add_label(collapse_ws("".join(finished["chunks"])))
        while self.table_stack:
            top = self.table_stack.pop()
            self._finish_cell(top)
            self._finish_row(top)
            if len(top["rows"]) >= 2:
                self.tables.append(top["rows"])

    def _finish_cell(self, top):
        if top["cell"] is None:
            return
        text = collapse_ws("".join(top["cell"]))
        if top["row"] is None:
            top["row"] = []
        top["row"].append(text)
        top["cell"] = None

    def _finish_row(self, top):
        if top["row"] is None:
            return
        top["rows"].append(top["row"])
        top["row"] = None

    def title(self):
        return collapse_ws("".join(self.title_chunks))


def format_jsonld_block(text):
    """Pretty-print JSON-LD with sorted keys. None if malformed."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


def extract_next_f_args(script_text):
    results = []
    pattern = re.compile(r'self\.__next_f\.push\s*\(')
    for m in pattern.finditer(script_text):
        start = m.end()
        depth = 1
        i = start
        in_quote = None
        escape = False
        while i < len(script_text) and depth > 0:
            ch = script_text[i]
            if in_quote:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == in_quote:
                    in_quote = None
            else:
                if ch in ('"', "'"):
                    in_quote = ch
                elif ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
            i += 1
        if depth == 0:
            results.append(script_text[start:i - 1].strip())
    return results


def parse_json_candidate(text):
    s = text.strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
        if isinstance(obj, (dict, list)):
            return obj
    except Exception:
        pass
    clean = re.sub(r'^[0-9a-fA-F]+:', '', s).strip()
    if clean != s:
        try:
            obj = json.loads(clean)
            if isinstance(obj, (dict, list)):
                return obj
        except Exception:
            pass
    return None


def has_digit_in_json(obj):
    dumped = json.dumps(obj, ensure_ascii=False)
    return any(c.isdigit() for c in dumped)


def is_scalar(v):
    return not isinstance(v, (dict, list))


def has_numeric(d):
    return any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in d.values())


def has_string(d):
    return any(isinstance(v, str) for v in d.values())


def collect_non_qualifying_scalars(d):
    scalars = {}
    if not isinstance(d, dict):
        return scalars
    for k, v in d.items():
        if is_scalar(v):
            scalars[k] = v
        elif isinstance(v, dict) and not has_qualifying_descendant(v):
            scalars.update(collect_non_qualifying_scalars(v))
    return scalars


def has_qualifying_descendant(o):
    if isinstance(o, dict):
        if any(has_qualifying_descendant(v) for v in o.values()):
            return True
        return has_numeric(o)
    elif isinstance(o, list):
        return any(has_qualifying_descendant(v) for v in o)
    return False


def flatten_row(d):
    flat = {}
    for k, v in d.items():
        if isinstance(v, dict):
            flat.update(flatten_row(v))
        else:
            flat[k] = v
    return flat


def extract_data_rows(payload):
    """Walk parsed payload recursively and emit qualifying data rows inside it.

    A data row is any dict that contains at least one numeric value and at least
    one string value, and that does not itself contain a nested dict or list
    among its values that also qualifies. Each qualifying dict is merged with its
    parent's scalar keys.
    """
    rows = []

    def walk(obj, parent_scalars=None):
        if parent_scalars is None:
            parent_scalars = {}

        if isinstance(obj, dict):
            child_has_qualifying = any(
                isinstance(v, (dict, list)) and has_qualifying_descendant(v)
                for v in obj.values()
            )

            if child_has_qualifying:
                context = {}
                for k, v in obj.items():
                    if is_scalar(v):
                        context[k] = v
                    elif isinstance(v, dict) and not has_qualifying_descendant(v):
                        context.update(collect_non_qualifying_scalars(v))
                merged_context = {**parent_scalars, **context}
                for k, v in obj.items():
                    if isinstance(v, (dict, list)):
                        walk(v, merged_context)
            else:
                merged = {**parent_scalars, **obj}
                if has_numeric(obj) and (has_string(obj) or has_string(merged)):
                    rows.append(merged)

        elif isinstance(obj, list):
            for item in obj:
                walk(item, parent_scalars)

    walk(payload)
    return rows


def extract_embedded_payloads(script_blocks):
    emitted = []
    for attrs, text in script_blocks:
        s_clean = text.strip()
        if not s_clean:
            continue
        t = _attr(attrs, "type").strip().lower()
        is_json_type = (t == "application/json" or t.startswith("application/json;"))
        looks_like_json = is_json_type or (s_clean.startswith("{") and s_clean.endswith("}")) or (s_clean.startswith("[") and s_clean.endswith("]"))
        if looks_like_json:
            try:
                obj = json.loads(s_clean)
                if isinstance(obj, (dict, list)):
                    if has_digit_in_json(obj):
                        emitted.append(("payload", obj))
                    continue
            except Exception:
                emitted.append(("note", "## note skipped malformed embedded payload"))
                continue

        if "self.__next_f.push" in s_clean:
            push_args = extract_next_f_args(s_clean)
            for arg_str in push_args:
                candidates = []
                try:
                    arr = json.loads(arg_str)
                    if isinstance(arr, list):
                        for item in arr:
                            if isinstance(item, str):
                                candidates.append(item)
                    elif isinstance(arr, str):
                        candidates.append(arr)
                except Exception:
                    for sm in re.finditer(r'"((?:[^"\\]|\\.)*)"', arg_str):
                        try:
                            candidates.append(json.loads('"' + sm.group(1) + '"'))
                        except Exception:
                            pass
                for cand in candidates:
                    obj = parse_json_candidate(cand)
                    if obj is not None and has_digit_in_json(obj):
                        emitted.append(("payload", obj))
    return emitted


def packet_header(source, url, title, digest, packed):
    """The five provenance lines every packet opens with."""
    return [
        f"## source {source}",
        f"## url {url}".rstrip() if url else "## url",
        f"## title {title}".rstrip() if title else "## title",
        f"## sha256 {digest}",
        f"## packed {packed}",
    ]


def pack_html(raw_bytes, source, url=None, packed=None):
    """Build a deterministic packet from raw HTML bytes.

    Same input bytes produce identical output bytes (on the same UTC date).
    Raises ClientRenderedError when nothing tabular survives.
    """
    if packed is None:
        packed = utc_today()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    html_text = raw_bytes.decode("utf-8", errors="replace")
    parser = PacketParser()
    parser.feed(html_text)
    parser.close()

    jsonld_emitted = []
    for block in parser.jsonld_blocks:
        formatted = format_jsonld_block(block)
        if formatted is None:
            jsonld_emitted.append(("note", "## note skipped malformed jsonld"))
        else:
            jsonld_emitted.append(("jsonld", formatted))

    embedded_emitted = extract_embedded_payloads(parser.script_blocks)

    emb_i = 0
    seen_rows = set()
    total_embedded_rows = 0
    truncated = False
    note_emitted = False
    embedded_lines = []

    for kind, val in embedded_emitted:
        if kind == "note":
            embedded_lines.append(val)
        else:
            rows = extract_data_rows(val)
            payload_rows = []
            for r in rows:
                flat_r = flatten_row(r)
                s = json.dumps(flat_r, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                if s in seen_rows:
                    continue
                seen_rows.add(s)
                if total_embedded_rows < 300:
                    payload_rows.append(s)
                    total_embedded_rows += 1
                else:
                    truncated = True
            if payload_rows:
                emb_i += 1
                embedded_lines.append(f"## embedded {emb_i}")
                embedded_lines.extend(payload_rows)
                if truncated and not note_emitted:
                    embedded_lines.append("## note embedded rows truncated at 300")
                    note_emitted = True

    if truncated and not note_emitted:
        embedded_lines.append("## note embedded rows truncated at 300")
        note_emitted = True

    has_surviving_embedded = (total_embedded_rows > 0)
    if (
        not parser.tables
        and not parser.labels
        and not any(kind == "jsonld" for kind, _text in jsonld_emitted)
        and not has_surviving_embedded
    ):
        raise ClientRenderedError(CLIENT_RENDERED_MSG)

    lines = packet_header(source, url, parser.title(), digest, packed)
    for i, rows in enumerate(parser.tables, 1):
        lines.append(f"## table {i}")
        for row in rows:
            lines.append("\t".join(row))
    jsonld_i = 0
    for kind, text in jsonld_emitted:
        if kind == "note":
            lines.append(text)
        else:
            jsonld_i += 1
            lines.append(f"## jsonld {jsonld_i}")
            lines.append(text)
    lines.extend(embedded_lines)
    if parser.labels:
        lines.append("## labels")
        for label in parser.labels:
            lines.append(label)
    return "\n".join(lines) + "\n"


def pack_file(html_file, source, url=None, out=None, packed=None):
    """Read html_file, pack it, write to out or stdout. Returns packet text."""
    try:
        with open(html_file, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise EffortError(f"{html_file}: cannot read: {e}")
    text = pack_html(raw, source, url=url, packed=packed)
    if out:
        parent = os.path.dirname(os.path.abspath(out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return text


def compose_extract_brief(packet_text):
    """Brief for the extract worker. Packet is embedded verbatim."""
    efforts = ", ".join(EFFORT_VALUES)
    return (
        "Extract per-effort benchmark rows from the packed page below.\n"
        "\n"
        "Write `rows.json` into the working directory as a JSON array of "
        "objects matching this schema:\n"
        "\n"
        f"{ROW_SCHEMA}\n"
        "\n"
        f"effort is lowercased and must be one of: {efforts}.\n"
        "\n"
        "Read the badge or label attached to a row and map it: wording that "
        "says the evaluator ran the model themselves (verified, official, "
        "reproduced, run by us) maps to `verified`; wording that says the "
        "score was submitted or reported by the model's vendor maps to "
        "`self-reported`; anything else, and any row whose badge you cannot "
        "see, is `unlabelled`. Guessing here is worse than `unlabelled`.\n"
        "\n"
        "every number you emit has to appear in the packet; if a cell is "
        "absent write null; never convert, scale, or infer a figure; a row "
        "you are unsure of belongs in `rows.json` with \"uncertain\": true "
        "rather than omitted.\n"
        "\n"
        "Keep the `deliverable` to a one-line count of rows written so the "
        "60-line return cap never truncates the data.\n"
        "\n"
        "--- packet ---\n"
        f"{packet_text}"
    )


def split_packet(packet_text, budget=DEFAULT_BUDGET):
    """Split packet_text into chunks that each fit within budget bytes.

    Each chunk retains the full packet header (## source, ## url, ## title,
    ## sha256, ## packed). Splits are made only on table or row boundaries,
    never mid-row. If the packet already fits within budget, returns [packet_text]
    unchanged (byte-identical).
    """
    if len(packet_text.encode("utf-8")) <= budget:
        return [packet_text]

    lines = packet_text.splitlines(keepends=True)
    header_lines = []
    content_lines = []
    in_header = True
    content_prefixes = ("## table", "## jsonld", "## embedded", "## labels", "## note")

    for line in lines:
        if in_header:
            if any(line.startswith(p) for p in content_prefixes):
                in_header = False
                content_lines.append(line)
            else:
                header_lines.append(line)
        else:
            content_lines.append(line)

    header_text = "".join(header_lines)
    header_bytes = len(header_text.encode("utf-8"))
    if header_bytes >= budget:
        raise EffortError(
            f"packet header ({header_bytes} bytes) exceeds chunk budget ({budget} bytes)"
        )

    sections = []
    cur_sec = []
    for line in content_lines:
        if line.startswith("## ") and any(line.startswith(p) for p in content_prefixes):
            if cur_sec:
                sections.append(cur_sec)
            cur_sec = [line]
        else:
            if cur_sec:
                cur_sec.append(line)
            else:
                cur_sec = [line]
    if cur_sec:
        sections.append(cur_sec)

    chunks = []
    current_lines = []
    current_bytes = header_bytes

    def flush():
        nonlocal current_lines, current_bytes
        if current_lines:
            chunks.append(header_text + "".join(current_lines))
            current_lines = []
            current_bytes = header_bytes

    for sec in sections:
        sec_bytes = sum(len(l.encode("utf-8")) for l in sec)
        if current_bytes + sec_bytes <= budget:
            current_lines.extend(sec)
            current_bytes += sec_bytes
            continue

        if current_lines and (header_bytes + sec_bytes <= budget):
            flush()
            current_lines.extend(sec)
            current_bytes += sec_bytes
            continue

        sec_tag = sec[0]
        if sec_tag.startswith("## table"):
            table_header = sec[1] if len(sec) > 1 else ""
            data_rows = sec[2:] if len(sec) > 2 else []
            prefix_lines = [sec_tag, table_header] if table_header else [sec_tag]
            prefix_bytes = sum(len(l.encode("utf-8")) for l in prefix_lines)
            first_row_bytes = len(data_rows[0].encode("utf-8")) if data_rows else 0
            if current_lines and (current_bytes + prefix_bytes + first_row_bytes > budget):
                flush()
            current_lines.extend(prefix_lines)
            current_bytes += prefix_bytes
            for r in data_rows:
                r_bytes = len(r.encode("utf-8"))
                if current_bytes + r_bytes <= budget:
                    current_lines.append(r)
                    current_bytes += r_bytes
                else:
                    flush()
                    current_lines.extend(prefix_lines)
                    current_bytes += prefix_bytes + r_bytes
                    current_lines.append(r)
        elif sec_tag.startswith("## embedded") or sec_tag.startswith("## labels"):
            prefix_lines = [sec_tag]
            prefix_bytes = sum(len(l.encode("utf-8")) for l in prefix_lines)
            data_rows = sec[1:]
            first_row_bytes = len(data_rows[0].encode("utf-8")) if data_rows else 0
            if current_lines and (current_bytes + prefix_bytes + first_row_bytes > budget):
                flush()
            current_lines.extend(prefix_lines)
            current_bytes += prefix_bytes
            for r in data_rows:
                r_bytes = len(r.encode("utf-8"))
                if current_bytes + r_bytes <= budget:
                    current_lines.append(r)
                    current_bytes += r_bytes
                else:
                    flush()
                    current_lines.extend(prefix_lines)
                    current_bytes += prefix_bytes + r_bytes
                    current_lines.append(r)
        else:
            if current_lines and (header_bytes + sec_bytes <= budget):
                flush()
            if current_bytes + sec_bytes <= budget:
                current_lines.extend(sec)
                current_bytes += sec_bytes
            else:
                for l in sec:
                    l_bytes = len(l.encode("utf-8"))
                    if current_bytes + l_bytes <= budget:
                        current_lines.append(l)
                        current_bytes += l_bytes
                    else:
                        flush()
                        current_lines.append(l)
                        current_bytes += l_bytes

    flush()
    return chunks


chunk_packet = split_packet


def row_key(row):
    """Identifying tuple for a benchmark row on (source, model, effort, benchmark)."""
    if not isinstance(row, dict):
        return id(row)
    return tuple(
        str(row.get(field) or "").strip().lower()
        for field in ROW_IDENTITY_FIELDS
    )


def deduplicate_rows(rows):
    """De-duplicate rows on (source, model, effort, benchmark), preserving first appearance."""
    seen = set()
    unique = []
    for row in rows:
        key = row_key(row)
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def combine_rows(*row_lists):
    """Combine multiple lists of rows and de-duplicate them on (source, model, effort, benchmark)."""
    flat = []
    for item in row_lists:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return deduplicate_rows(flat)


def delegate_path():
    """Path to delegate.py. The sibling script wins; PATH is the fallback."""
    sibling = os.path.join(os.path.dirname(os.path.abspath(__file__)), "delegate.py")
    if os.path.isfile(sibling):
        return sibling
    found = shutil.which("delegate.py")
    if found:
        return found
    raise EffortError("delegate.py: not beside effort.py and not on PATH")


def extract_rows(packet_path, out_dir, lane=None, budget=DEFAULT_BUDGET):
    """Dispatch an LLM worker to write rows.json. Needs network; tests skip this."""
    if lane is None:
        lane = DEFAULT_LANE
    os.makedirs(out_dir, exist_ok=True)
    try:
        with open(packet_path, encoding="utf-8") as f:
            packet_text = f.read()
    except OSError as e:
        raise EffortError(f"{packet_path}: cannot read: {e}")
    if packet_text.startswith(f"## source {AA_SOURCE}\n"):
        raise EffortError(
            f"{packet_path}: an Artificial Analysis packet goes to no worker; "
            "run `effort.py aa`, which reads the page's own dataset"
        )

    chunks = split_packet(packet_text, budget=budget)

    if len(chunks) == 1:
        brief_path = os.path.join(out_dir, "extract-brief.md")
        with open(brief_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(compose_extract_brief(packet_text))
        cmd = [
            sys.executable, delegate_path(), "dispatch",
            "--lane", lane,
            "--brief", brief_path,
            "--cwd", os.path.abspath(out_dir),
            "--write", os.path.abspath(out_dir),
        ]
        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            raise EffortError("delegate.py: not found on PATH")
        except subprocess.CalledProcessError as e:
            raise EffortError(f"delegate.py dispatch failed with exit {e.returncode}")
        return

    chunk_rows_list = []
    for i, chunk_text in enumerate(chunks, 1):
        chunk_dir = os.path.join(out_dir, f"chunk-{i}")
        os.makedirs(chunk_dir, exist_ok=True)
        brief_path = os.path.join(chunk_dir, "extract-brief.md")
        with open(brief_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(compose_extract_brief(chunk_text))
        cmd = [
            sys.executable, delegate_path(), "dispatch",
            "--lane", lane,
            "--brief", brief_path,
            "--cwd", os.path.abspath(chunk_dir),
            "--write", os.path.abspath(chunk_dir),
        ]
        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            raise EffortError("delegate.py: not found on PATH")
        except subprocess.CalledProcessError as e:
            raise EffortError(f"delegate.py dispatch for chunk {i} failed with exit {e.returncode}")

        chunk_rows_path = os.path.join(chunk_dir, "rows.json")
        chunk_rows_list.append(load_rows(chunk_rows_path))

    combined = combine_rows(*chunk_rows_list)
    combined_path = os.path.join(out_dir, "rows.json")
    with open(combined_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(format_json(combined))


def normalize_numeric_token(token):
    """Strip $, thousands separators, and a trailing %. Return Decimal or None."""
    s = token.strip()
    if s.startswith("$"):
        s = s[1:]
    if s.endswith("%"):
        s = s[:-1]
    s = s.replace(",", "").strip()
    if not s or s in {".", "-", "-.", "+", "+."}:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def value_to_decimal(value):
    """JSON number to Decimal. None for bool/None/unparseable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        return normalize_numeric_token(value)
    return None


def format_reason_value(value):
    """Render a numeric field for an unsourced reason string."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(Decimal(str(value)), "f")
    return str(value)


def packet_numbers(packet_text):
    """Set of Decimal values found as numeric tokens in the packet."""
    found = set()
    for tok in NUM_TOKEN.findall(packet_text):
        n = normalize_numeric_token(tok)
        if n is not None:
            found.add(n)
    return found


def occurs_ci(haystack, needle):
    if needle is None:
        return False
    text = str(needle).strip()
    if not text:
        return False
    return text.lower() in haystack.lower()


def check_row(row, packet_text, numbers):
    """Return a list of rejection reasons (empty means accept)."""
    reasons = []
    effort = row.get("effort")
    effort_s = "" if effort is None else str(effort).strip()
    effort_key = effort_s.lower()
    if effort_key not in EFFORT_VALUES:
        reasons.append(f"bad effort {effort_s}")
    model = row.get("model")
    if not occurs_ci(packet_text, model):
        reasons.append("unsourced model")
    printed = EFFORT_PRINTED.get(effort_key, (effort_s,))
    if effort_key in EFFORT_VALUES and not any(occurs_ci(packet_text, word) for word in printed):
        reasons.append("unsourced effort")
    elif effort_key not in EFFORT_VALUES and effort_s and not occurs_ci(packet_text, effort_s):
        reasons.append("unsourced effort")
    for field in NUMERIC_FIELDS:
        if field not in row:
            continue
        value = row[field]
        if value is None:
            continue
        dec = value_to_decimal(value)
        if dec is None or dec not in numbers:
            reasons.append(f"unsourced {field}={format_reason_value(value)}")
    if "provenance" in row:
        provenance = row["provenance"]
        if provenance not in PROVENANCE_VALUES:
            reasons.append(f"bad provenance {provenance}")
        elif provenance in PROVENANCE_STEMS:
            stems = PROVENANCE_STEMS[provenance]
            model_s = "" if model is None else str(model).strip()
            matched_lines = [
                line for line in packet_text.splitlines()
                if model_s and effort_s and model_s.lower() in line.lower() and effort_s.lower() in line.lower()
            ]
            if not matched_lines:
                reasons.append(f"unsourced provenance={provenance}")
            elif not any(any(stem in line.lower() for stem in stems) for line in matched_lines):
                reasons.append(f"unsourced provenance={provenance}")
    return reasons


def check_rows(rows, packet_text):
    """Split rows into (accepted, rejected), each with a reasons list."""
    numbers = packet_numbers(packet_text)
    accepted = []
    rejected = []
    for row in rows:
        if not isinstance(row, dict):
            item = {"value": row, "reasons": ["not an object"]}
            rejected.append(item)
            continue
        item = dict(row)
        item["reasons"] = check_row(row, packet_text, numbers)
        if item["reasons"]:
            rejected.append(item)
        else:
            accepted.append(item)
    return accepted, rejected


def load_rows(path):
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        raise EffortError(f"{path}: cannot read: {e}")
    try:
        doc = json.loads(content)
    except json.JSONDecodeError as e:
        raise EffortError(
            f"{path}: line {e.lineno}, column {e.colno}: JSON syntax error: {e.msg}"
        )
    if not isinstance(doc, list):
        raise EffortError(f"{path}: document: must be a JSON array")
    return doc


def load_packet(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise EffortError(f"{path}: cannot read: {e}")


def check_files(rows_path, packet_path, out_dir=None, quiet=False):
    """Write accepted.json and rejected.json. Returns (checked, accepted, rejected).

    `quiet` is for a caller that prints its own line: the wizard refreshes the
    rows itself and says so on its start page (ticket 33)."""
    if out_dir is None:
        out_dir = os.getcwd()
    os.makedirs(out_dir, exist_ok=True)
    rows = load_rows(rows_path)
    packet_text = load_packet(packet_path)
    accepted, rejected = check_rows(rows, packet_text)
    with open(os.path.join(out_dir, "accepted.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(format_json(accepted))
    with open(os.path.join(out_dir, "rejected.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(format_json(rejected))
    checked = len(rows)
    verified = sum(1 for r in accepted if r.get("provenance") == "verified")
    self_reported = sum(1 for r in accepted if r.get("provenance") == "self-reported")
    if not quiet:
        print(
            f"checked={checked} accepted={len(accepted)} rejected={len(rejected)} "
            f"verified={verified} self-reported={self_reported}"
        )
    return checked, accepted, rejected


def run_pipeline(html_file, source, out_dir, url=None, lane=None, budget=DEFAULT_BUDGET):
    """pack, then extract, then check. Stops at the first failure."""
    os.makedirs(out_dir, exist_ok=True)
    packet_path = os.path.join(out_dir, "packet.txt")
    pack_file(html_file, source, url=url, out=packet_path)
    extract_rows(packet_path, out_dir, lane=lane, budget=budget)
    rows_path = os.path.join(out_dir, "rows.json")
    return check_files(rows_path, packet_path, out_dir=out_dir)


# --- Artificial Analysis: the dataset the page embeds -------------------------
# Every /models/<slug> page on artificialanalysis.ai carries the whole comparison
# dataset in its Next.js flight payload, one JSON object per model variant, so no
# worker reads it: a parser copies numbers out of JSON it did not write, and
# `check` verifies each one against that payload, which is the packet.
# llm-cost-frontier's update.py (catalystneuro, BSD-3) reads the same payload and
# was the reference for where to look.

AA_SOURCE = "aa"
SOURCES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "assets", "sources.json")
# Every variant object carries this key, and nothing else on the page does.
AA_MARKER_KEY = "intelligenceIndexCostPerTask"
# payload field -> the benchmark the row names.
AA_COMPONENTS = (
    ("terminalbenchV21", "Terminal-Bench 2.1"),
    ("automationBenchPartialScore", "AutomationBench"),
    ("lcr", "AA-LCR"),
    ("ifbench", "IFBench"),
    ("omniscience", "Omniscience"),
    ("gpqa", "GPQA Diamond"),
    ("gdpvalNormalized", "GDPval"),
    ("mmmuPro", "MMMU-Pro"),
)
# The composite is emitted so a reader can see it, flagged `composite` so the
# carry page never decides on it: the sources file says its weighting is not
# published.
AA_COMPOSITE = ("intelligenceIndex", "Artificial Analysis Intelligence Index")
# The index's cost and output tokens per task: one figure per variant, the same
# on every benchmark row of that variant.
AA_COST_FIELD = "intelligenceIndexCostPerTask.cost.total"
AA_TOKENS_FIELD = "intelligenceIndexOutputTokensPerTask.output"
AA_EFFORT_WORDS = tuple(e for e in EFFORT_VALUES if e not in ("none", "unspecified"))
FLIGHT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
HTML_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def flight_payload(html_text):
    """The page's Next.js flight payload: every `push([1, "..."])` string, joined."""
    chunks = FLIGHT_CHUNK.findall(html_text)
    if not chunks:
        raise EffortError("no Next.js flight payload on the page; the site layout may have changed")
    return "".join(json.loads(f'"{chunk}"') for chunk in chunks)


def _enclosing_brace(text, index):
    """Offset of the `{` opening the object that contains `index`, or None.

    It counts braces walking back and does not track strings, so a brace inside
    a string can mislead it. The caller parses what it finds and keeps it only
    if the marker is that object's own key, so a wrong start costs a variant,
    never a wrong row.
    """
    depth = 0
    for j in range(index, -1, -1):
        ch = text[j]
        if ch == "}":
            depth += 1
        elif ch == "{":
            if depth == 0:
                return j
            depth -= 1
    return None


def aa_variants(payload):
    """Each variant object in the payload once, in payload order."""
    decoder = json.JSONDecoder()
    variants, seen = [], set()
    for m in re.finditer(f'"{AA_MARKER_KEY}"', payload):
        start = _enclosing_brace(payload, m.start())
        if start is None:
            continue
        try:
            obj, _end = decoder.raw_decode(payload, start)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or AA_MARKER_KEY not in obj:
            continue
        name = obj.get("name")
        if not isinstance(name, str) or name in seen:
            continue
        seen.add(name)
        variants.append(obj)
    return variants


def _aa_effort(variant_name):
    """The effort a variant name prints, or None.

    `GPT-5.6 Sol (high)` and `Claude Fable 5.1 (Adaptive Reasoning, High Effort,
    Default Fallback)` are both `high`; `(Non-reasoning)` is `none`. A name with
    no effort word in its closing parentheses — `(Reasoning)`, or none at all —
    says nothing a lane could be set to.
    """
    m = re.search(r"\(([^()]*)\)\s*$", variant_name)
    if not m:
        return None
    for part in m.group(1).split(","):
        word = part.strip().lower()
        if word == "non-reasoning":
            return "none"
        if word.endswith(" effort"):
            word = word[: -len(" effort")].strip()
        if word in AA_EFFORT_WORDS:
            return word
    return None


def _dig(obj, path):
    for key in path.split("."):
        obj = obj.get(key) if isinstance(obj, dict) else None
    return obj


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def aa_rows(variants, url, observed):
    """One row per variant per component score it has.

    `model` is the release name (`GPT-5.6 Sol`) and `effort` the word in the
    variant name, so the catalog resolves the row the way it resolves any other
    source's. Beyond the worker row schema each row keeps `variant`, the name
    the page printed, and `fields`, the payload field behind each number.
    """
    rows = []
    for variant in variants:
        name = variant["name"]
        effort = _aa_effort(name)
        if effort is None:
            continue
        release = _dig(variant, "release.name")
        model = release if isinstance(release, str) and release.strip() else name.split(" (")[0]
        cost = _number(_dig(variant, AA_COST_FIELD))
        tokens = _number(_dig(variant, AA_TOKENS_FIELD))
        for field, benchmark in AA_COMPONENTS + (AA_COMPOSITE,):
            score = _number(variant.get(field))
            if score is None:
                continue
            row = {
                "source": AA_SOURCE, "url": url, "model": model, "effort": effort,
                "benchmark": benchmark, "score": score, "score_unit": None,
                "cost_usd": cost, "tokens": tokens, "observed": observed,
                # The page has no per-row badge to read, so nothing here can
                # claim `verified`; that AA runs every model itself is a fact
                # about the source, recorded in sources.json.
                "provenance": "unlabelled",
                # No lane runs at `none`, and ticket 15 keeps it uncertain.
                "uncertain": effort == "none",
                "variant": name,
                "fields": {"score": field, "cost_usd": AA_COST_FIELD, "tokens": AA_TOKENS_FIELD},
            }
            if (field, benchmark) == AA_COMPOSITE:
                row["composite"] = True
            rows.append(row)
    return rows


def aa_extract(raw_bytes, url=None, observed=None):
    """(packet, rows) for one Artificial Analysis model page.

    The packet is the whole flight payload under the usual provenance header,
    verbatim, so `check` verifies the rows against the page and nothing else.
    """
    if observed is None:
        observed = utc_today()
    html_text = raw_bytes.decode("utf-8", errors="replace")
    payload = flight_payload(html_text)
    variants = aa_variants(payload)
    if not variants:
        raise EffortError("the page payload holds no model dataset; the site layout may have changed")
    title_match = HTML_TITLE.search(html_text)
    title = collapse_ws(html.unescape(title_match.group(1))) if title_match else ""
    digest = hashlib.sha256(raw_bytes).hexdigest()
    lines = packet_header(AA_SOURCE, url, title, digest, observed)
    lines += ["## payload", payload.rstrip("\n")]
    return "\n".join(lines) + "\n", aa_rows(variants, url, observed)


def source_url(source_id):
    """The page the sources file approves for `source_id`."""
    try:
        with open(SOURCES_PATH, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise EffortError(f"{SOURCES_PATH}: cannot read: {e}")
    url = ((doc.get("sources") or {}).get(source_id) or {}).get("url")
    if not url:
        raise EffortError(f"{SOURCES_PATH}: source {source_id} has no url")
    return url


def fetch_page(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (delegate effort.py)"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as e:
        raise EffortError(f"{url}: cannot fetch: {e}")


def run_aa(out_dir, url=None, html_file=None, quiet=False):
    """Read one Artificial Analysis model page, write packet.txt and rows.json,
    then check them. `html_file` reads a saved page instead of fetching; its
    `url` is then only what the rows record. `quiet` leaves the lines to a
    caller that prints its own, as the wizard's refresh does (ticket 33)."""
    if html_file:
        try:
            with open(html_file, "rb") as f:
                raw = f.read()
        except OSError as e:
            raise EffortError(f"{html_file}: cannot read: {e}")
    else:
        url = url or source_url(AA_SOURCE)
        raw = fetch_page(url)
    packet_text, rows = aa_extract(raw, url=url)
    os.makedirs(out_dir, exist_ok=True)
    packet_path = os.path.join(out_dir, "packet.txt")
    rows_path = os.path.join(out_dir, "rows.json")
    with open(packet_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(packet_text)
    with open(rows_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(format_json(rows))
    if not quiet:
        print(f"aa: {len({r['variant'] for r in rows})} variants with an effort, {len(rows)} rows")
    return check_files(rows_path, packet_path, out_dir=out_dir, quiet=quiet)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="effort.py",
        description=(
            "Scrape-then-convert pipeline for per-effort benchmark data. "
            "Stage 3 is the trust boundary: an LLM may not originate a number."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pack = sub.add_parser("pack", help="pack HTML into a deterministic packet")
    p_pack.add_argument("html_file", help="path to HTML file")
    p_pack.add_argument("--source", required=True, help="source id")
    p_pack.add_argument("--url", default=None, help="source URL")
    p_pack.add_argument("-o", "--out", default=None, help="output packet path")

    p_extract = sub.add_parser("extract", help="extract rows from a packet via LLM")
    p_extract.add_argument("--packet", required=True, help="path to packet.txt")
    p_extract.add_argument("--out-dir", required=True, help="output directory")
    p_extract.add_argument(
        "--lane", default=DEFAULT_LANE,
        help=f"delegate lane (default {DEFAULT_LANE}; fallback {FALLBACK_LANE})",
    )
    p_extract.add_argument(
        "--budget", type=int, default=DEFAULT_BUDGET,
        help=f"maximum byte size per packet chunk (default {DEFAULT_BUDGET})",
    )

    p_check = sub.add_parser("check", help="reject rows whose numbers are not in the packet")
    p_check.add_argument("--rows", required=True, help="path to rows.json")
    p_check.add_argument("--packet", required=True, help="path to packet.txt")
    p_check.add_argument(
        "--out-dir", default=None,
        help="directory for accepted.json and rejected.json",
    )

    p_run = sub.add_parser("run", help="pack, extract, then check")
    p_run.add_argument("html_file", help="path to HTML file")
    p_run.add_argument("--source", required=True, help="source id")
    p_run.add_argument("--out-dir", required=True, help="output directory")
    p_run.add_argument("--url", default=None, help="source URL")
    p_run.add_argument(
        "--lane", default=DEFAULT_LANE,
        help=f"delegate lane (default {DEFAULT_LANE}; fallback {FALLBACK_LANE})",
    )
    p_run.add_argument(
        "--budget", type=int, default=DEFAULT_BUDGET,
        help=f"maximum byte size per packet chunk (default {DEFAULT_BUDGET})",
    )

    p_aa = sub.add_parser(
        "aa", help="read an Artificial Analysis model page's own dataset, then check",
    )
    p_aa.add_argument("--out-dir", required=True, help="output directory")
    p_aa.add_argument(
        "--url", default=None,
        help="model page to fetch (default: the page sources.json approves)",
    )
    p_aa.add_argument("--html", default=None, help="saved page to read instead of fetching")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "pack":
            pack_file(args.html_file, args.source, url=args.url, out=args.out)
        elif args.cmd == "extract":
            extract_rows(args.packet, args.out_dir, lane=args.lane, budget=args.budget)
        elif args.cmd == "check":
            _checked, _accepted, rejected = check_files(
                args.rows, args.packet, out_dir=args.out_dir,
            )
            if rejected:
                sys.exit(1)
        elif args.cmd == "run":
            _checked, _accepted, rejected = run_pipeline(
                args.html_file, args.source, args.out_dir,
                url=args.url, lane=args.lane, budget=args.budget,
            )
            if rejected:
                sys.exit(1)
        elif args.cmd == "aa":
            _checked, _accepted, rejected = run_aa(
                args.out_dir, url=args.url, html_file=args.html,
            )
            if rejected:
                sys.exit(1)
    except ClientRenderedError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(2)
    except EffortError as e:
        sys.stderr.write(f"effort: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
