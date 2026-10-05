#!/usr/bin/env python3
"""Tests for match, notes, run and queue (stdlib; a stub LLM server on loopback).

notes   chunked map-reduce with no truncation (ollama API), openai API, header,
        skip on unchanged fingerprints and rerun on a changed transcript,
        refusal of a non-loopback endpoint and of a redirect, a malformed answer,
        a hand-edited notes.md kept
match   a matched event with invitees, a tie (unmatched), source none, a weekly
        recurring event with TZID and EXDATE, an ics_url that is not file://
run     state transitions (notes-ready, failed with reason), --if-enabled,
        queue picks new and stale recordings, skips failed unless --retry
egress  (macOS, models present) the whole `run` (match, transcribe with the real
        models, notes) inside a sandbox that allows only localhost; a request to
        the internet from the same sandbox fails

Run:  make test-meeting-notes
"""
import http.server, json, os, pathlib, platform, shutil, subprocess, sys, tempfile, threading

sys.dont_write_bytecode = True  # no __pycache__ under ~/.hammerspoon
ROOT = pathlib.Path(__file__).resolve().parents[3]
CLI = ROOT / "stow/hammerspoon/.hammerspoon/bin/meeting-notes"
WORK = pathlib.Path(tempfile.mkdtemp(prefix="mn-pipeline."))
SECTIONS = "## Summary\n- {tag}\n\n## Decisions\n- None.\n\n## Action items\n- [S1] send the quote\n\n## Open questions\n- None.\n"
LOCAL_ONLY = ('(version 1)(allow default)(deny network*)'
              '(allow network-outbound (remote ip "localhost:*"))(allow network-outbound (remote unix-socket))')


class Stub(http.server.BaseHTTPRequestHandler):
    """Speaks /api/chat (ollama) and /v1/chat/completions (openai); records each request."""
    log, mode = [], "ok"

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.log.append({"path": self.path, "body": body})
        if Stub.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{PORT}/followed")  # loopback: a followed redirect stays local
            self.end_headers()
            return
        if Stub.mode == "error":
            self.send_response(500)
            self.end_headers()
            return
        system = body["messages"][0]["content"]
        tag = "reduce" if "combine partial" in system else "map"
        content = "Sure! Here are notes." if Stub.mode == "bad" else SECTIONS.format(tag=tag)
        reply = {"message": {"role": "assistant", "content": content}} if self.path == "/api/chat" else \
            {"choices": [{"message": {"role": "assistant", "content": content}}]}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
PORT = SERVER.server_port


def config(path, **sections):
    lines = []
    for sec, vals in sections.items():
        lines.append(f"[{sec}]")
        for k, v in vals.items():
            lines.append(f'{k} = {json.dumps(v) if isinstance(v, (str, bool)) else v}')
    path.write_text("\n".join(lines) + "\n")
    return dict(os.environ, MEETING_NOTES_CONFIG=str(path))


def cli(env, *args, sandbox=None):
    cmd = [str(CLI), *args]
    if sandbox:
        cmd = ["/usr/bin/sandbox-exec", "-p", sandbox, *cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


SEGMENTS = [("S1", "system", "Good morning, let us review the bracket schedule and the open risks today."),
            ("mic", "mic", "I can review the load cases on Friday afternoon and send comments."),
            ("S2", "system", "The supplier confirmed a two week delay on the bracket parts."),
            ("S1", "system", "Please send the quote from the second supplier before Wednesday."),
            ("mic", "mic", "I will ask them today and forward the numbers when they reply.")]


def make_rec(name, start="2026-10-05T15:00:00.000Z", end="2026-10-05T15:30:00.000Z", transcript=True):
    """A recording folder with recording.json, a stand-in master.caf and a transcript."""
    rec = WORK / "rec" / name
    rec.mkdir(parents=True, mode=0o700)
    (rec / "master.caf").write_bytes(b"stand-in")
    (rec / "recording.json").write_text(json.dumps({
        "format_version": 1, "id": name, "state": "recorded", "legs": {"mic": {"present": True},
                                                                      "system": {"present": True}},
        "requested": {"start": start, "end": end}, "actual": {"start": start, "end": end}}))
    if transcript:
        segs = [{"id": i + 1, "start": i * 10.0, "end": i * 10.0 + 8, "source": src, "speaker": sp, "text": t,
                 "text_clean": t, "words": []} for i, (sp, src, t) in enumerate(SEGMENTS)]
        (rec / "transcript.json").write_text(json.dumps({
            "format_version": 1, "segments": segs,
            "speakers": [{"id": s, "source": src} for s, src in (("mic", "mic"), ("S1", "system"), ("S2", "system"))]}))
    return rec


def report(name, ok, detail=""):
    print(f"[{name}] {'PASS' if ok else 'FAIL'} {detail}".rstrip())
    return ok


def pipeline_state(rec):
    return (json.loads((rec / "recording.json").read_text()).get("pipeline") or {})


# ---------- notes ----------

def notes_cases():
    res = []
    rec = make_rec("notes-a")
    env = config(WORK / "n1.toml", notes={"endpoint": f"http://127.0.0.1:{PORT}", "model": "stub", "api": "ollama",
                                          "chunk_chars": 200})
    Stub.log.clear()
    rc, out = cli(env, "notes", str(rec))
    maps = [r for r in Stub.log if "combine partial" not in r["body"]["messages"][0]["content"]]
    reduces = [r for r in Stub.log if "combine partial" in r["body"]["messages"][0]["content"]]
    sent = "\n".join(r["body"]["messages"][1]["content"] for r in maps)
    every_text = all(all(w in sent for w in t.split()) for _, _, t in SEGMENTS)
    within = all(len(r["body"]["messages"][1]["content"].split("Transcript part", 1)[1]) < 200 + 40 for r in maps)
    notes = (rec / "notes.md").read_text() if (rec / "notes.md").exists() else ""
    header = all(x in notes for x in ("# Notes: notes-a", "- Transcript: sha256", "- Model: stub (ollama API",
                                       "- Prompt: notes-v1", "## Action items"))
    mode = oct((rec / "notes.md").stat().st_mode & 0o777) if notes else None
    res.append(report("notes-chunked", rc == 0 and len(maps) >= 3 and len(reduces) >= 1 and every_text and within
                      and header and mode == "0o600",
                      f"maps={len(maps)} reduces={len(reduces)} all-text-sent={every_text} mode={mode}"))

    Stub.log.clear()
    rc, out = cli(env, "notes", str(rec))
    res.append(report("notes-skip", rc == 0 and "unchanged" in out and not Stub.log))
    t = json.loads((rec / "transcript.json").read_text())
    t["segments"][0]["text"] = t["segments"][0]["text_clean"] = "A changed first sentence about the schedule."
    (rec / "transcript.json").write_text(json.dumps(t))
    Stub.log.clear()
    rc, out = cli(env, "notes", str(rec))
    res.append(report("notes-rerun", rc == 0 and len(Stub.log) > 0))

    (rec / "notes.md").write_text((rec / "notes.md").read_text() + "\nmy own line\n")
    rc, out = cli(env, "notes", str(rec), "--force")
    res.append(report("notes-hand-edit", rc == 4 and "edited by hand" in out))

    rec = make_rec("notes-b")
    env2 = config(WORK / "n2.toml", notes={"endpoint": f"http://localhost:{PORT}", "model": "stub", "api": "openai"})
    Stub.log.clear()
    rc, out = cli(env2, "notes", str(rec))
    res.append(report("notes-openai", rc == 0 and [r["path"] for r in Stub.log] == ["/v1/chat/completions"] * 2,
                      f"calls={[r['path'] for r in Stub.log]}"))

    rec = make_rec("notes-c")
    for name, endpoint in (("notes-refuse-remote", "http://192.0.2.10:11434"),
                           ("notes-refuse-name", "http://example.com:11434")):
        env3 = config(WORK / "n3.toml", notes={"endpoint": endpoint, "model": "stub"})
        rc, out = cli(env3, "notes", str(rec))
        res.append(report(name, rc == 1 and "local only" in out and not (rec / "notes.md").exists(), out.strip()[-90:]))

    Stub.mode = "redirect"
    rc, out = cli(env, "notes", str(rec))
    res.append(report("notes-refuse-redirect", rc == 1 and "redirect" in out and not (rec / "notes.md").exists()))
    Stub.mode = "bad"
    rc, out = cli(env, "notes", str(rec))
    res.append(report("notes-bad-answer", rc == 1 and "lacks" in out and not (rec / "notes.md").exists()))
    Stub.mode = "ok"
    rc, out = cli(config(WORK / "n4.toml"), "notes", str(rec))
    res.append(report("notes-off", rc == 5 and "off" in out))
    return res


# ---------- match ----------

def ics(*events):
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n"


def vevent(uid, summary, start, end, attendees=(), extra=""):
    att = "".join(f"ATTENDEE;CN={a}:mailto:{a.lower()}@example.com\r\n" for a in attendees)
    return (f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:{summary}\r\nDTSTART:{start}\r\nDTEND:{end}\r\n{att}{extra}"
            "END:VEVENT\r\n")


def match_case(name, calendar, rec_start, rec_end, source="ics_file"):
    rec = make_rec(name, rec_start, rec_end, transcript=False)
    cal = WORK / f"{name}.ics"
    cal.write_text(calendar)
    path = str(cal) if source == "ics_file" else (f"file://{cal}" if source == "ics_url" else "http://example.com/x.ics")
    env = config(WORK / f"{name}.toml", match={"source": "ics_url" if source.startswith("ics_url") or
                                                source == "http" else source, "path": path})
    rc, out = cli(env, "match", str(rec))
    m = json.loads((rec / "meeting.json").read_text()) if (rec / "meeting.json").exists() else None
    return rc, out, m


def match_cases():
    res = []
    cal = ics(vevent("a", "Design review", "20261005T150000Z", "20261005T153000Z", ["Alpha", "Bravo", "Charlie"]),
              vevent("b", "Lunch", "20261005T170000Z", "20261005T180000Z"))
    rc, out, m = match_case("match-ok", cal, "2026-10-05T15:01:10.000Z", "2026-10-05T15:28:00.000Z")
    res.append(report("match-ok", rc == 0 and m["state"] == "matched" and m["event"]["title"] == "Design review"
                      and m["event"]["invitee_count"] == 3, f"{m and m['state']} {m and m['reason']}"))

    cal = ics(vevent("a", "Sync one", "20261005T150000Z", "20261005T153000Z"),
              vevent("b", "Sync two", "20261005T150000Z", "20261005T153000Z"))
    rc, out, m = match_case("match-tie", cal, "2026-10-05T15:00:00.000Z", "2026-10-05T15:30:00.000Z")
    res.append(report("match-tie", rc == 0 and m["state"] == "unmatched" and "ambiguous" in m["reason"]
                      and len(m["candidates"]) == 2))

    rec = make_rec("match-none", transcript=False)
    rc, out = cli(config(WORK / "mn.toml", match={"source": "none"}), "match", str(rec))
    m = json.loads((rec / "meeting.json").read_text())
    res.append(report("match-none", rc == 0 and m["state"] == "unmatched" and "no calendar" in m["reason"]))

    weekly = vevent("w", "Weekly sync", "20260907T110000", "20260907T113000",
                    ["Alpha", "Bravo"], "RRULE:FREQ=WEEKLY;BYDAY=MO\r\nEXDATE;TZID=America/New_York:20260928T110000\r\n")
    weekly = weekly.replace("DTSTART:", "DTSTART;TZID=America/New_York:").replace("DTEND:", "DTEND;TZID=America/New_York:")
    # 2026-10-05 is a Monday; 11:00 New York (EDT) is 15:00 UTC
    rc, out, m = match_case("match-weekly", ics(weekly), "2026-10-05T15:00:30.000Z", "2026-10-05T15:29:00.000Z")
    ok1 = rc == 0 and m["state"] == "matched" and m["event"]["start"].startswith("2026-10-05T11:00:00")
    rc, out, m = match_case("match-exdate", ics(weekly), "2026-09-28T15:00:30.000Z", "2026-09-28T15:29:00.000Z")
    res.append(report("match-weekly", ok1 and m["state"] == "unmatched", "occurrence matched; EXDATE skipped"))

    rc, out, m = match_case("match-url", cal, "2026-10-05T15:00:00.000Z", "2026-10-05T15:30:00.000Z", source="http")
    res.append(report("match-url-refused", rc == 1 and "file://" in out and m is None))
    return res


# ---------- run and queue ----------

def run_cases():
    res = []
    root = WORK / "rec"
    base = {"paths": {"recordings": str(root)}, "run": {"auto_run": True, "transcribe": False},
            "notes": {"endpoint": f"http://127.0.0.1:{PORT}", "model": "stub"}}
    env = config(WORK / "r1.toml", **base)
    rec = make_rec("run-ok")
    rc, out = cli(env, "run", str(rec))
    res.append(report("run-notes-ready", rc == 0 and pipeline_state(rec).get("state") == "notes-ready", out.strip()[-80:]))

    rec = make_rec("run-fail")
    Stub.mode = "error"
    rc, out = cli(env, "run", str(rec))
    st = pipeline_state(rec)
    res.append(report("run-failed", rc == 1 and st.get("state") == "failed" and "HTTP 500" in (st.get("reason") or ""),
                      str(st)))
    Stub.mode = "ok"

    off = config(WORK / "r2.toml", **dict(base, run={"auto_run": False, "transcribe": False}))
    rc, out = cli(off, "run", str(make_rec("run-off")), "--if-enabled")
    rc2, out2 = cli(off, "queue", "--if-enabled")
    res.append(report("run-if-enabled", rc == 5 and rc2 == 5))

    stale = make_rec("run-stale")
    meta = json.loads((stale / "recording.json").read_text())
    meta["pipeline"] = {"state": "processing"}
    (stale / "recording.json").write_text(json.dumps(meta))
    for p in root.iterdir():  # leave only the folders this case is about
        if p.name not in ("run-ok", "run-fail", "run-stale", "run-off"):
            shutil.rmtree(p)
    rc, out = cli(env, "queue")
    res.append(report("queue", rc == 0 and pipeline_state(stale).get("state") == "notes-ready"
                      and pipeline_state(root / "run-off").get("state") == "notes-ready"
                      and pipeline_state(root / "run-fail").get("state") == "failed", out.strip().replace("\n", " | ")))
    rc, out = cli(env, "queue", "--retry")
    res.append(report("queue-retry", rc == 0 and pipeline_state(root / "run-fail").get("state") == "notes-ready"))
    return res


def config_case():
    """The committed example config parses and its keys are all known settings."""
    sys.path.insert(0, str(CLI.parent.parent))
    from meeting_notes.common import DEFAULTS, parse_toml_subset
    ex = parse_toml_subset((ROOT / "tools/meeting-notes/config.example.toml").read_text())
    unknown = [f"{s}.{k}" for s, v in ex.items() for k in v if k not in DEFAULTS.get(s, {})]
    return report("config-example", not unknown and ex["run"]["auto_run"] is False, f"unknown={unknown}")


# ---------- egress ----------

def egress_case():
    models = pathlib.Path.home() / "Library/Application Support/FluidAudio/Models"
    if platform.system() != "Darwin" or not (pathlib.Path.home() / ".local/bin/meeting-asr").exists() \
            or not (models / "speaker-diarization").exists():
        print("[egress] SKIP (macOS with meeting-asr and the models only)")
        return True
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import transcribe_test as tt
    work = WORK / "egress"
    work.mkdir()
    rec = tt.make_recording(work)
    meta = json.loads((rec / "recording.json").read_text())
    meta["actual"] = {"start": "2026-10-05T15:00:10.000Z", "end": "2026-10-05T15:00:50.000Z"}
    (rec / "recording.json").write_text(json.dumps(meta))
    cal = work / "cal.ics"
    cal.write_text(ics(vevent("e", "Bracket review", "20261005T150000Z", "20261005T153000Z", ["Alpha"])))
    # no_network = false: the outer sandbox below covers every process; sandboxes cannot nest
    env = config(work / "e.toml", transcribe={"no_network": False},
                 match={"source": "ics_file", "path": str(cal)},
                 notes={"endpoint": f"http://127.0.0.1:{PORT}", "model": "stub"})
    rc, out = cli(env, "run", str(rec), sandbox=LOCAL_ONLY)
    st = pipeline_state(rec)
    t = json.loads((rec / "transcript.json").read_text()) if (rec / "transcript.json").exists() else {}
    probe = subprocess.run(["/usr/bin/sandbox-exec", "-p", LOCAL_ONLY, "/usr/bin/python3", "-c",
                            "import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)"],
                           capture_output=True, text=True)
    sys_speakers = sorted({s["speaker"] for s in t.get("segments", []) if s["source"] == "system"})
    return report("egress", rc == 0 and st.get("state") == "notes-ready" and probe.returncode != 0
                  and t.get("max_speakers", {}).get("from") == "meeting.json invitees + 1",
                  f"state={st.get('state')} internet-blocked={probe.returncode != 0} speakers={sys_speakers} "
                  f"bound={t.get('max_speakers')} {out.strip()[-120:] if rc else ''}")


if __name__ == "__main__":
    try:
        results = notes_cases() + match_cases() + run_cases() + [config_case(), egress_case()]
    finally:
        SERVER.shutdown()
        if "--keep" in sys.argv[1:]:
            print(f"kept: {WORK}")
        else:
            shutil.rmtree(WORK, ignore_errors=True)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    sys.exit(0 if all(results) else 1)
