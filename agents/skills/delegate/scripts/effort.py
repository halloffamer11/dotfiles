#!/usr/bin/env python3
"""effort.py — scrape-then-convert pipeline for per-effort benchmark data.

Three stages, one trust boundary:

    HTML  --[1 pack: deterministic]-->  packet.txt
    packet.txt  --[2 extract: LLM]-->  rows.json
    rows.json + packet.txt  --[3 check: deterministic]-->  accepted.json / rejected.json

An LLM may select and restructure text. It may not originate a number.
Stage 3 enforces that mechanically.

Stage 3 catches invented distinctive numbers and cannot vouch for small
integers, so a human still reads accepted.json. A badge that sits in different
markup from its row will degrade to a rejection rather than a false accept:
a missed badge is recoverable, a false verified is not.

Default extract lane is flash-high@agy; terra-high@codex is the fallback
for packets that lane handles badly.

CLI forms:
  effort.py pack <html-file> --source <id> [--url <url>] [-o <out>]
  effort.py extract --packet <file> --out-dir <dir> [--lane <lane>]
  effort.py check --rows <rows.json> --packet <file> [--out-dir <dir>]
  effort.py run <html-file> --source <id> --out-dir <dir>
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

DEFAULT_LANE = "flash-high@agy"
FALLBACK_LANE = "terra-high@codex"
EFFORT_VALUES = (
    "none", "low", "medium", "high", "xhigh", "max", "ultra", "unspecified",
)
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

    url_value = url if url else ""
    lines = [
        f"## source {source}",
        f"## url {url_value}".rstrip() if url_value else "## url",
        f"## title {parser.title()}".rstrip() if parser.title() else "## title",
        f"## sha256 {digest}",
        f"## packed {packed}",
    ]
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


def extract_rows(packet_path, out_dir, lane=None):
    """Dispatch an LLM worker to write rows.json. Needs network; tests skip this."""
    if lane is None:
        lane = DEFAULT_LANE
    os.makedirs(out_dir, exist_ok=True)
    try:
        with open(packet_path, encoding="utf-8") as f:
            packet_text = f.read()
    except OSError as e:
        raise EffortError(f"{packet_path}: cannot read: {e}")
    brief_path = os.path.join(out_dir, "extract-brief.md")
    with open(brief_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(compose_extract_brief(packet_text))
    cmd = [
        "delegate.py", "dispatch",
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
    if effort_key in EFFORT_VALUES and not occurs_ci(packet_text, effort_s):
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


def check_files(rows_path, packet_path, out_dir=None):
    """Write accepted.json and rejected.json. Returns (checked, accepted, rejected)."""
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
    print(
        f"checked={checked} accepted={len(accepted)} rejected={len(rejected)} "
        f"verified={verified} self-reported={self_reported}"
    )
    return checked, accepted, rejected


def run_pipeline(html_file, source, out_dir, url=None, lane=None):
    """pack, then extract, then check. Stops at the first failure."""
    os.makedirs(out_dir, exist_ok=True)
    packet_path = os.path.join(out_dir, "packet.txt")
    pack_file(html_file, source, url=url, out=packet_path)
    extract_rows(packet_path, out_dir, lane=lane)
    rows_path = os.path.join(out_dir, "rows.json")
    return check_files(rows_path, packet_path, out_dir=out_dir)


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

    args = parser.parse_args(argv)

    try:
        if args.cmd == "pack":
            pack_file(args.html_file, args.source, url=args.url, out=args.out)
        elif args.cmd == "extract":
            extract_rows(args.packet, args.out_dir, lane=args.lane)
        elif args.cmd == "check":
            _checked, _accepted, rejected = check_files(
                args.rows, args.packet, out_dir=args.out_dir,
            )
            if rejected:
                sys.exit(1)
        elif args.cmd == "run":
            _checked, _accepted, rejected = run_pipeline(
                args.html_file, args.source, args.out_dir,
                url=args.url, lane=args.lane,
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
