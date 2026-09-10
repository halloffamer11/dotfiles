#!/usr/bin/env python3
"""test_effort.py — unit and CLI tests for effort.py. Run: python3 tests/test_effort.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.abspath(os.path.join(HERE, "..", "scripts"))
EFFORT_PY = os.path.join(SCRIPTS_DIR, "effort.py")
FIXTURES = os.path.join(HERE, "fixtures")

sys.path.insert(0, SCRIPTS_DIR)
import effort

fails = 0


def record(name, ok, detail=""):
    global fails
    if ok:
        print(f"PASS {name}")
    else:
        fails += 1
        print(f"FAIL {name}: {detail}")


def run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, EFFORT_PY, *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def fixture(*parts):
    return os.path.join(FIXTURES, *parts)


def make_row(**overrides):
    row = {
        "source": "demo",
        "url": "https://example.com/board",
        "model": "gpt-4",
        "effort": "high",
        "benchmark": "swe-bench",
        "score": 72,
        "score_unit": None,
        "cost_usd": 10,
        "tokens": 2048,
        "observed": "2026-01-01",
        "uncertain": False,
    }
    row.update(overrides)
    return row


def check_cli(rows, td, packet_path=None):
    rows_path = os.path.join(td, "rows.json")
    with open(rows_path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return run_cli(
        "check",
        "--rows", rows_path,
        "--packet", packet_path or fixture("sourced.packet.txt"),
        "--out-dir", td,
    )


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


with open(fixture("sourced.packet.txt"), encoding="utf-8") as f:
    base_packet = f.read()

# 1. pack on a two-table fixture emits both tables as TSV with headers
res = run_cli("pack", fixture("two_tables.html"), "--source", "demo")
out = res.stdout
table1 = out.find("## table 1")
table2 = out.find("## table 2")
source_idx = out.find("## source")
ok = (
    res.returncode == 0
    and "## source demo" in out
    and "## title Two Table Leaderboard" in out
    and "## table 1" in out
    and "## table 2" in out
    and "Model\tEffort\tScore" in out
    and "gpt-4\thigh\t19" in out
    and "Model\tCost" in out
    and "gpt-4\t$143.5" in out
    and out.startswith("## source ")
    and source_idx != -1 and table1 != -1 and table2 != -1
    and source_idx < table1 < table2
)
record("pack two tables emits tsv with headers", ok, f"rc={res.returncode}, out={out[:200]}")

# 2. pack is byte-identical across two runs of the same input
res1 = run_cli("pack", fixture("two_tables.html"), "--source", "demo")
res2 = run_cli("pack", fixture("two_tables.html"), "--source", "demo")
with open(fixture("two_tables.html"), "rb") as f:
    raw = f.read()
a = effort.pack_html(raw, "demo", packed="2026-01-01")
b = effort.pack_html(raw, "demo", packed="2026-01-01")
ok = (
    res1.returncode == 0
    and res2.returncode == 0
    and res1.stdout == res2.stdout
    and a == b
)
record("pack byte-identical across runs", ok, f"rc1={res1.returncode}, rc2={res2.returncode}")

# 3. pack on a table-free fixture exits 2 with the client-rendered message
res = run_cli("pack", fixture("client_rendered.html"), "--source", "demo")
ok = (
    res.returncode == 2
    and "no static tabular data; page is likely client-rendered" in res.stderr
    and res.stdout == ""
    and "Traceback" not in res.stderr
    and "Traceback" not in res.stdout
)
record("pack table-free exits 2 client-rendered", ok, f"rc={res.returncode}, stderr={res.stderr}")

# 4. pack keeps JSON-LD text and drops <script>/<style> content
res = run_cli("pack", fixture("jsonld_and_script.html"), "--source", "demo")
out = res.stdout
ctx = out.find('"@context"')
name = out.find('"name"')
score = out.find('"score"')
ok = (
    res.returncode == 0
    and "## jsonld 1" in out
    and '"name": "Leaderboard"' in out
    and '"score": 19' in out
    and "## note skipped malformed jsonld" in out
    and "secret_should_not_appear" not in out
    and "secret-css" not in out
    and "window.__DATA__" not in out
    and ctx != -1 and name != -1 and score != -1
    and ctx < name < score
)
record("pack keeps jsonld drops script style", ok, f"rc={res.returncode}, out={out[:200]}")

# 5. div-based row carrying a title holding score and cost emits both under ## labels
res = run_cli("pack", fixture("div_row_title.html"), "--source", "demo")
out = res.stdout
labels_idx = out.find("## labels")
labels_section = out[labels_idx:] if labels_idx != -1 else ""
ok = (
    res.returncode == 0
    and labels_idx != -1
    and "88.5" in labels_section
    and "42.0" in labels_section
    and "model-x · high — score 88.5, cost $42.0" in labels_section
)
record("pack div row title emits labels", ok, f"rc={res.returncode}, out={out[:200]}")

# 6. aria-label is picked up on the same terms as title
html = b"""<!DOCTYPE html>
<html>
<head><title>Aria Board</title></head>
<body>
  <div aria-label="model-y score 91.2 cost $15.5"></div>
  <div aria-label="Sort by score"></div>
  <div aria-label="1"></div>
</body>
</html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
labels_idx = packet.find("## labels")
labels_section = packet[labels_idx:] if labels_idx != -1 else ""
ok = (
    labels_idx != -1
    and "model-y score 91.2 cost $15.5" in labels_section
    and "Sort by score" not in labels_section
    and "\n1\n" not in labels_section
)
record("pack aria-label picked up same as title", ok, packet)

# 7. title with no digit is skipped
html = b"""<!DOCTYPE html>
<html>
<head><title>Title Filter</title></head>
<body>
  <button title="Sort by name">Sort</button>
  <div title="model-z score 55.0">content</div>
</body>
</html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
labels_idx = packet.find("## labels")
labels_section = packet[labels_idx:] if labels_idx != -1 else ""
no_digit_html = b"<html><head><title>T</title></head><body><button title='Sort by name'>Sort</button></body></html>"
raised_cr = False
try:
    effort.pack_html(no_digit_html, "demo")
except effort.ClientRenderedError:
    raised_cr = True
ok = (
    labels_idx != -1
    and "model-z score 55.0" in labels_section
    and "Sort by name" not in labels_section
    and raised_cr
)
record("pack title without digit is skipped", ok)

# 8. sr-only span containing a digit is captured
html = b"""<!DOCTYPE html>
<html>
<head><title>SR Board</title></head>
<body>
  <span class="sr-only"> 4 accepted, 3 broken by a counterexample, 0 blind, of 20 runs </span>
  <span class="visually-hidden"> 10 retries remaining </span>
  <span class="screen-reader-text"> Page 1 of 5 </span>
  <span class="sr-only"> no digits here </span>
</body>
</html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
labels_idx = packet.find("## labels")
labels_section = packet[labels_idx:] if labels_idx != -1 else ""
ok = (
    labels_idx != -1
    and "4 accepted, 3 broken by a counterexample, 0 blind, of 20 runs" in labels_section
    and "10 retries remaining" in labels_section
    and "Page 1 of 5" in labels_section
    and "no digits here" not in labels_section
)
record("pack sr-only span captured", ok, packet)

# 9. determinism still holds with labels present
with open(fixture("div_row_title.html"), "rb") as f:
    raw = f.read()
a = effort.pack_html(raw, "demo", packed="2026-01-01")
b = effort.pack_html(raw, "demo", packed="2026-01-01")
res1 = run_cli("pack", fixture("div_row_title.html"), "--source", "demo")
res2 = run_cli("pack", fixture("div_row_title.html"), "--source", "demo")
ok = (
    a == b
    and res1.returncode == 0
    and res2.returncode == 0
    and res1.stdout == res2.stdout
)
record("pack determinism with labels present", ok)

# 10. page with only a digit-bearing label and no table does not exit 2
res = run_cli("pack", fixture("div_row_title.html"), "--source", "demo")
ok = (
    res.returncode == 0
    and "no static tabular data" not in res.stderr
    and "## labels" in res.stdout
    and "## table" not in res.stdout
)
record("pack digit label only does not exit 2", ok, res.stderr)

# 11. against tests/fixtures/real_swerb_sample.html, packet contains 143.5 and 28.5
res = run_cli("pack", fixture("real_swerb_sample.html"), "--source", "swerb")
ok = (
    res.returncode == 0
    and "143.5" in res.stdout
    and "28.5" in res.stdout
)
record("pack real swerb sample contains expected figures", ok, res.stderr)

# 12. check accepts a row whose every number is on the page
row = make_row(score=19, cost_usd=143.5, tokens=2048)
with tempfile.TemporaryDirectory() as td:
    res = check_cli([row], td)
    accepted = load_json(os.path.join(td, "accepted.json"))
    rejected = load_json(os.path.join(td, "rejected.json"))
    ok = (
        res.returncode == 0
        and res.stdout.strip() == "checked=1 accepted=1 rejected=0 verified=0 self-reported=0"
        and len(accepted) == 1
        and accepted[0]["reasons"] == []
        and rejected == []
    )
    record("check accepts sourced row", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 13. check rejects a planted hallucination — cost_usd 999.99
row = make_row(score=19, cost_usd=999.99, tokens=2048)
not_in_pkt = "999.99" not in base_packet
with tempfile.TemporaryDirectory() as td:
    res = check_cli([row], td)
    rejected = load_json(os.path.join(td, "rejected.json"))
    accepted = load_json(os.path.join(td, "accepted.json"))
    ok = (
        not_in_pkt
        and res.returncode == 1
        and res.stdout.strip() == "checked=1 accepted=0 rejected=1 verified=0 self-reported=0"
        and accepted == []
        and len(rejected) == 1
        and "unsourced cost_usd=999.99" in rejected[0]["reasons"]
    )
    record("check rejects planted hallucination", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 14. 19 in the packet matches score 19.0; $143.5 matches 143.50
row = make_row(score=19.0, cost_usd=143.50, tokens=2048)
with tempfile.TemporaryDirectory() as td:
    res = check_cli([row], td)
    accepted = load_json(os.path.join(td, "accepted.json"))
    ok = (
        res.returncode == 0
        and res.stdout.strip() == "checked=1 accepted=1 rejected=0 verified=0 self-reported=0"
        and len(accepted) == 1
        and accepted[0]["reasons"] == []
    )
    record("check matches numeric equivalents", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 15. check rejects effort "reasoning-high" as out of enum
row = make_row(effort="reasoning-high", score=19, cost_usd=143.5)
with tempfile.TemporaryDirectory() as td:
    res = check_cli([row], td)
    rejected = load_json(os.path.join(td, "rejected.json"))
    ok = (
        res.returncode == 1
        and len(rejected) == 1
        and "bad effort reasoning-high" in rejected[0]["reasons"]
    )
    record("check rejects out of enum effort", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 16. row with provenance "verified" against packet with supporting stem on row line is accepted
row = make_row(score=19, cost_usd=143.5, tokens=2048, provenance="verified")
with tempfile.TemporaryDirectory() as td:
    packet_path = os.path.join(td, "packet.txt")
    packet_with_verified = base_packet.replace(
        "gpt-4\thigh\tswe-bench\t19\t$143.5\t2048",
        "gpt-4\thigh\tswe-bench\t19\t$143.5\t2048\tVerified",
    )
    with open(packet_path, "w", encoding="utf-8") as f:
        f.write(packet_with_verified)
    res = check_cli([row], td, packet_path=packet_path)
    accepted = load_json(os.path.join(td, "accepted.json"))
    ok = (
        res.returncode == 0
        and res.stdout.strip() == "checked=1 accepted=1 rejected=0 verified=1 self-reported=0"
        and len(accepted) == 1
        and accepted[0]["reasons"] == []
        and accepted[0]["provenance"] == "verified"
    )
    record("check accepts verified provenance with supporting stem", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 17. same row against a packet with no stem anywhere is rejected with unsourced provenance=verified
row = make_row(score=19, cost_usd=143.5, tokens=2048, provenance="verified")
no_verif_stem = "verif" not in base_packet.lower() and "official" not in base_packet.lower()
with tempfile.TemporaryDirectory() as td:
    res = check_cli([row], td)
    rejected = load_json(os.path.join(td, "rejected.json"))
    ok = (
        no_verif_stem
        and res.returncode == 1
        and res.stdout.strip() == "checked=1 accepted=0 rejected=1 verified=0 self-reported=0"
        and len(rejected) == 1
        and "unsourced provenance=verified" in rejected[0]["reasons"]
    )
    record("check rejects unsourced verified provenance", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 18. packet carrying verification in prose but not on row line rejects verified row
row = make_row(score=19, cost_usd=143.5, tokens=2048, provenance="verified")
with tempfile.TemporaryDirectory() as td:
    packet_path = os.path.join(td, "packet.txt")
    packet_prose_verification = base_packet + "\n## notes\ngrading method uses six agentic verifiers and verification\n"
    with open(packet_path, "w", encoding="utf-8") as f:
        f.write(packet_prose_verification)
    res = check_cli([row], td, packet_path=packet_path)
    rejected = load_json(os.path.join(td, "rejected.json"))
    accepted = load_json(os.path.join(td, "accepted.json"))
    ok = (
        "verification" in packet_prose_verification
        and res.returncode == 1
        and res.stdout.strip() == "checked=1 accepted=0 rejected=1 verified=0 self-reported=0"
        and accepted == []
        and len(rejected) == 1
        and "unsourced provenance=verified" in rejected[0]["reasons"]
    )
    record("check rejects verified row when verification in prose not on row line", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 19. provenance: "trusted" is rejected as bad provenance trusted
row = make_row(score=19, cost_usd=143.5, tokens=2048, provenance="trusted")
with tempfile.TemporaryDirectory() as td:
    res = check_cli([row], td)
    rejected = load_json(os.path.join(td, "rejected.json"))
    ok = (
        res.returncode == 1
        and len(rejected) == 1
        and "bad provenance trusted" in rejected[0]["reasons"]
    )
    record("check rejects out of enum provenance", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 20. row with no provenance key at all is accepted and counted as unlabelled
row = make_row(score=19, cost_usd=143.5, tokens=2048)
no_prov_key = "provenance" not in row
with tempfile.TemporaryDirectory() as td:
    res = check_cli([row], td)
    accepted = load_json(os.path.join(td, "accepted.json"))
    ok = (
        no_prov_key
        and res.returncode == 0
        and res.stdout.strip() == "checked=1 accepted=1 rejected=0 verified=0 self-reported=0"
        and len(accepted) == 1
        and accepted[0]["reasons"] == []
    )
    record("check accepts missing provenance as unlabelled", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 21. summary line reports the verified / self-reported counts correctly
row_verified = make_row(model="gpt-4", effort="high", score=19, cost_usd=143.5, tokens=2048, provenance="verified")
row_self_reported = make_row(model="gpt-4", effort="high", score=19, cost_usd=143.5, tokens=2048, provenance="self-reported")
row_unlabelled = make_row(model="gpt-4", effort="high", score=19, cost_usd=143.5, tokens=2048, provenance="unlabelled")
row_missing = make_row(model="gpt-4", effort="high", score=19, cost_usd=143.5, tokens=2048)
row_rejected_verified = make_row(model="gpt-4", effort="high", score=19, cost_usd=999.99, tokens=2048, provenance="verified")
rows = [row_verified, row_self_reported, row_unlabelled, row_missing, row_rejected_verified]
with tempfile.TemporaryDirectory() as td:
    packet_path = os.path.join(td, "packet.txt")
    packet_with_stems = base_packet.replace(
        "gpt-4\thigh\tswe-bench\t19\t$143.5\t2048",
        "gpt-4\thigh\tswe-bench\t19\t$143.5\t2048\tVerified Community",
    )
    with open(packet_path, "w", encoding="utf-8") as f:
        f.write(packet_with_stems)
    res = check_cli(rows, td, packet_path=packet_path)
    accepted = load_json(os.path.join(td, "accepted.json"))
    rejected = load_json(os.path.join(td, "rejected.json"))
    ok = (
        res.returncode == 1
        and res.stdout.strip() == "checked=5 accepted=4 rejected=1 verified=1 self-reported=1"
        and len(accepted) == 4
        and len(rejected) == 1
    )
    record("check summary line reports provenance counts", ok, f"rc={res.returncode} out={res.stdout} err={res.stderr}")

# 22. extract brief contains required rules
brief = effort.compose_extract_brief("## source demo\n")
ok = (
    "every number you emit has to appear in the packet" in brief
    and "if a cell is absent write null" in brief
    and "never convert, scale, or infer a figure" in brief
    and "`rows.json`" in brief
    and '"uncertain": true' in brief
    and "rather than omitted" in brief
    and "Keep the `deliverable` to a one-line count" in brief
    and "## source demo" in brief
    and '"provenance": "verified" | "self-reported" | "unlabelled"' in brief
    and "guessing here is worse than `unlabelled`" in brief.lower()
)
record("extract brief contains required rules", ok)

# 23. fixture with self.__next_f.push([1,"{\"a\":1,\"model\":\"test\"}"]) emits the object
html = r"""<!DOCTYPE html>
<html>
<head><title>Next.js Page</title></head>
<body>
<script>self.__next_f.push([1,"{\"a\":1,\"model\":\"test\"}"])</script>
</body>
</html>""".encode("utf-8")
packet = effort.pack_html(html, "demo", packed="2026-01-01")
ok = (
    "## embedded 1" in packet
    and ('"a":1' in packet or '"a": 1' in packet)
)
record("pack emits next_f payload", ok, packet)

# 24. bare <script> holding JSON object emits it
html = b"""<!DOCTYPE html>
<html>
<head><title>Bare Script Page</title></head>
<body>
<script>
{
  "metric": 42,
  "model": "test-model"
}
</script>
</body>
</html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
ok = (
    "## embedded 1" in packet
    and ('"metric":42' in packet or '"metric": 42' in packet)
    and ('"model":"test-model"' in packet or '"model": "test-model"' in packet)
)
record("pack emits bare json script", ok, packet)

# 25. script whose JSON is malformed produces a note without exception or abort
html = b"""<!DOCTYPE html>
<html>
<head><title>Malformed Script Page</title></head>
<body>
<script>{not valid json 123}</script>
<table><tr><th>Header</th><th>Val</th></tr><tr><td>Row</td><td>100</td></tr></table>
</body>
</html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
ok = (
    "## note skipped malformed embedded payload" in packet
    and "## table 1" in packet
    and "Row\t100" in packet
)
record("pack malformed json produces note without abort", ok, packet)

# 26. parsed object with no digit anywhere is skipped
html_no_digit = b"""<!DOCTYPE html>
<html>
<head><title>No Digit Page</title></head>
<body>
<script>{"name": "alpha", "items": ["foo", "bar"]}</script>
</body>
</html>"""
client_err = False
try:
    effort.pack_html(html_no_digit, "demo")
except effort.ClientRenderedError:
    client_err = True

html_with_table = b"""<!DOCTYPE html>
<html>
<head><title>No Digit With Table</title></head>
<body>
<script>{"name": "alpha", "items": ["foo", "bar"]}</script>
<table><tr><th>Model</th><th>Score</th></tr><tr><td>alpha</td><td>95</td></tr></table>
</body>
</html>"""
packet = effort.pack_html(html_with_table, "demo", packed="2026-01-01")
ok = (
    client_err
    and "## embedded" not in packet
    and "alpha" in packet
    and "## table 1" in packet
)
record("pack skips parsed object with no digit", ok, packet)

# 27. determinism holds with embedded payloads present
html = r"""<!DOCTYPE html>
<html>
<head><title>Determinism</title></head>
<body>
<script>self.__next_f.push([1, "{\"a\": 2, \"m\": 3, \"model\": \"test1\", \"z\": 1}"])</script>
<script type="application/json">{"k1": 10, "k2": 20, "model": "test2"}</script>
</body>
</html>""".encode("utf-8")
p1 = effort.pack_html(html, "demo", packed="2026-01-01")
p2 = effort.pack_html(html, "demo", packed="2026-01-01")
ok = (
    p1 == p2
    and "## embedded 1" in p1
    and "## embedded 2" in p1
    and (
        (p1.find('"a":2') < p1.find('"m":3') < p1.find('"z":1'))
        or (p1.find('"a": 2') < p1.find('"m": 3') < p1.find('"z": 1'))
    )
    and (
        (p1.find('"k1":10') < p1.find('"k2":20'))
        or (p1.find('"k1": 10') < p1.find('"k2": 20'))
    )
)
record("pack determinism with embedded payloads", ok)

# 28. 300-row cap truncates deterministically and emits note
big_obj = [{"model": f"k_{i:04d}", "score": i} for i in range(500)]
html = f'<!DOCTYPE html><html><body><script type="application/json">{json.dumps(big_obj)}</script></body></html>'.encode("utf-8")
p1 = effort.pack_html(html, "demo", packed="2026-01-01")
p2 = effort.pack_html(html, "demo", packed="2026-01-01")
lines1 = p1.splitlines()
emb_idx = lines1.index("## embedded 1")
note_idx = lines1.index("## note embedded rows truncated at 300")
ok = (
    p1 == p2
    and note_idx - emb_idx - 1 == 300
    and "## note embedded rows truncated at 300" in p1
)
record("pack 300-row cap truncates deterministically", ok)

# 29. against tests/fixtures/real_tbench_sample.html, packet contains reasoning_effort, 58.18, and GPT-6 Astra
res = run_cli("pack", fixture("real_tbench_sample.html"), "--source", "tbench")
ok = (
    res.returncode == 0
    and "reasoning_effort" in res.stdout
    and "58.18" in res.stdout
    and "GPT-6 Astra" in res.stdout
)
record("pack real tbench sample contains expected figures", ok, f"rc={res.returncode}")

# 30. A nested fixture where the qualifying dict is three levels deep: the row is emitted and its container is not
html = b"""<!DOCTYPE html>
<html><body>
<script>
{
  "level1": {
    "level2": {
      "level3": {
        "metric": 42,
        "model": "deep-model"
      }
    }
  }
}
</script>
</body></html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
ok = (
    '{"metric":42,"model":"deep-model"}' in packet
    and "level1" not in packet
    and "level2" not in packet
    and "level3" not in packet
)
record("nested fixture three levels deep emits row not container", ok, packet)

# 31. A row merges scalar keys from its parent (model name from one branch, metric from another, on one line)
html = b"""<!DOCTYPE html>
<html><body>
<script>
{
  "metadata": {
    "model": "branch-model"
  },
  "metrics": {
    "score": 95.5,
    "unit": "%"
  }
}
</script>
</body></html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
expected_row = '{"model":"branch-model","score":95.5,"unit":"%"}'
ok = (
    expected_row in packet
    and "\n" + expected_row + "\n" in packet
)
record("row merges scalar keys from parent branches", ok, packet)

# 32. Rows are emitted one per line as compact JSON with sorted keys
html = b"""<!DOCTYPE html>
<html><body>
<script>
[
  {"z": 1, "a": "first", "m": 50},
  {"y": "second", "b": 20, "k": 30}
]
</script>
</body></html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
lines = packet.splitlines()
row1 = '{"a":"first","m":50,"z":1}'
row2 = '{"b":20,"k":30,"y":"second"}'
ok = (
    row1 in lines
    and row2 in lines
    and lines.index(row1) + 1 == lines.index(row2)
    and not any(line.startswith("  ") for line in [row1, row2])
)
record("rows emitted one per line compact with sorted keys", ok, packet)

# 33. Duplicate identical rows appear once
html = b"""<!DOCTYPE html>
<html><body>
<script>
[
  {"model": "gpt-4", "score": 90},
  {"score": 90, "model": "gpt-4"},
  {"model": "gpt-4", "score": 90}
]
</script>
</body></html>"""
packet = effort.pack_html(html, "demo", packed="2026-01-01")
count = packet.count('{"model":"gpt-4","score":90}')
ok = (
    count == 1
)
record("duplicate identical rows appear once", ok, packet)

# 34. The 300-row cap emits the note deterministically
big_list = [{"model": f"m_{i:04d}", "score": i} for i in range(350)]
html = f'<!DOCTYPE html><html><body><script type="application/json">{json.dumps(big_list)}</script></body></html>'.encode("utf-8")
p1 = effort.pack_html(html, "demo", packed="2026-01-01")
p2 = effort.pack_html(html, "demo", packed="2026-01-01")
lines1 = p1.splitlines()
emb_idx = lines1.index("## embedded 1")
note_idx = lines1.index("## note embedded rows truncated at 300")
ok = (
    p1 == p2
    and note_idx - emb_idx - 1 == 300
    and "## note embedded rows truncated at 300" in p1
)
record("The 300-row cap emits the note deterministically", ok)

# 35. Regression: against tests/fixtures/real_tbench_sample.html, packet contains at least 5 distinct reasoning_effort values for GPT-6 Astra, and under 700 lines
res = run_cli("pack", fixture("real_tbench_sample.html"), "--source", "tbench")
lines = res.stdout.splitlines()
astra_efforts = set()
for line in lines:
    if "GPT-6 Astra" in line:
        try:
            row = json.loads(line)
            if "reasoning_effort" in row:
                astra_efforts.add(row["reasoning_effort"])
        except Exception:
            pass
ok = (
    res.returncode == 0
    and len(astra_efforts) >= 5
    and len(lines) < 700
)
record("regression: real tbench sample has 5 distinct reasoning_effort values and < 700 lines", ok, f"efforts={astra_efforts}, lines={len(lines)}")

sys.exit(1 if fails else 0)
