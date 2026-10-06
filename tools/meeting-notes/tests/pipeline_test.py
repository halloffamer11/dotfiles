#!/usr/bin/env python3
"""Tests for the VoiceInk settings reader, enhancement, run and queue.

VoiceInk's settings come from fake plists ($MEETING_NOTES_VOICEINK_PLIST) and its
system template from a fake app binary ($MEETING_NOTES_VOICEINK_BINARY); a stub
command stands in for the Local CLI tool.

voiceink    active mode chosen by id; CurrentTranscriptionModel when the mode
            has no model; the system template found once, refused when ambiguous
enhance     off by default; skipped (with the reason) when VoiceInk's mode has it
            off, uses another provider, or has no template; the Local CLI call
            matches VoiceInk's (zsh -lc, VOICEINK_* variables, full prompt as an
            argument or on stdin, system prompt inside VoiceInk's template, the
            transcript in <TRANSCRIPT>), runs outside the recording folder;
            skip, rerun, hand edit, timeout
run         (macOS, models present) transcribed with the skip reason recorded,
            enhanced, failed with a reason, --if-enabled; queue picks new and
            stale recordings and retries failed ones only with --retry
egress      (macOS, models present) the whole run inside a sandbox that denies
            all network access; a request to the internet from it fails

Run:  make test-meeting-notes
"""
import json, os, pathlib, platform, plistlib, shutil, subprocess, sys, tempfile

sys.dont_write_bytecode = True  # no __pycache__ under ~/.hammerspoon
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CLI = ROOT / "stow/hammerspoon/.hammerspoon/bin/meeting-notes"
sys.path.insert(0, str(CLI.parent.parent))
sys.path.insert(0, str(HERE))
from meeting_notes import voiceink  # noqa: E402
import transcribe_test as tt  # noqa: E402

WORK = pathlib.Path(tempfile.mkdtemp(prefix="mn-pipeline."))
NO_NETWORK = "(version 1)(allow default)(deny network*)"
STUB, STUB_LOG = WORK / "local-cli-stub", WORK / "local-cli-stub.log"
STUB.write_text(f"""#!/usr/bin/python3
# Stand-in for a Local CLI tool: records what VoiceInk's contract hands it.
import json, os, sys, time
data = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
with open({str(STUB_LOG)!r}, "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": data,
                        "env": {{k: v for k, v in os.environ.items() if k.startswith("VOICEINK_")}}}}) + "\\n")
if os.environ.get("STUB_MODE") == "sleep":
    time.sleep(30)
print("The enhanced transcript.")
""")
STUB.chmod(0o755)
FAKE_BINARY = WORK / "VoiceInk"
FAKE_TEMPLATE = "<SYSTEM_INSTRUCTIONS>\n<TASK>\nFake rules for <TRANSCRIPT>.\n</TASK>\n<TASK_INSTRUCTIONS>\n%@\n</TASK_INSTRUCTIONS>\n</SYSTEM_INSTRUCTIONS>"
FAKE_BINARY.write_bytes(b"\x00\x01junk" + FAKE_TEMPLATE.encode() + b"\x00more" + FAKE_TEMPLATE.encode() + b"\x00")
ARG_TEMPLATE = f'{STUB} "$VOICEINK_FULL_PROMPT"'
STDIN_TEMPLATE = f"{STUB} --from-stdin"


def report(name, ok, detail=""):
    print(f"[{name}] {'PASS' if ok else 'FAIL'} {detail}".rstrip())
    return ok


def stub_calls():
    return [json.loads(l) for l in STUB_LOG.read_text().splitlines()] if STUB_LOG.exists() else []


def plist(name, model="parakeet-unified-0.6b", enhancement_on=True, provider="Local CLI", template=ARG_TEMPLATE,
          system_instructions=True, timeout=None):
    extra = {"mode": {"isAIEnhancementEnabled": enhancement_on, **({"selectedAIProvider": provider} if provider else {})},
             "localCLICommandTemplate": template}
    if timeout:
        extra["localCLITimeoutSeconds"] = timeout
    path = tt.voiceink_plist(WORK / f"{name}.plist", model, enhancement=extra)
    if not system_instructions:
        d = plistlib.loads(open(path, "rb").read())
        prompts = json.loads(d["customPrompts"])
        prompts[0]["useSystemInstructions"] = False
        d["customPrompts"] = json.dumps(prompts).encode()
        open(path, "wb").write(plistlib.dumps(d))
    return path


def env(name, vi_plist, **sections):
    cfg = WORK / f"{name}.toml"
    lines = []
    for sec, vals in sections.items():
        lines.append(f"[{sec}]")
        lines += [f"{k} = {json.dumps(v)}" for k, v in vals.items()]
    cfg.write_text("\n".join(lines) + "\n")
    return dict(os.environ, MEETING_NOTES_CONFIG=str(cfg), MEETING_NOTES_VOICEINK_PLIST=vi_plist,
                MEETING_NOTES_VOICEINK_BINARY=str(FAKE_BINARY))


def cli(e, *args, sandbox=None):
    cmd = [str(CLI), *args]
    if sandbox:
        cmd = ["/usr/bin/sandbox-exec", "-p", sandbox, *cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, env=e)
    return r.returncode, r.stdout + r.stderr


def text_rec(name):
    """A recording folder with a transcript.md only (enough for enhance)."""
    rec = WORK / "rec" / name
    rec.mkdir(parents=True, mode=0o700)
    (rec / "master.caf").write_bytes(b"stand-in")
    (rec / "recording.json").write_text(json.dumps({"format_version": 1, "id": name, "state": "recorded",
                                                    "legs": {"mic": {"present": True}, "system": {"present": True}}}))
    (rec / "transcript.md").write_text("# Transcript: x\n\n- Model: m\n\n---\n\n"
                                       "**[00:01] System:** um the supplier confirmed a delay\n\n"
                                       "**[00:05] Mic:** please send the quote before Wednesday\n")
    return rec


def pipeline_state(rec):
    return json.loads((rec / "recording.json").read_text()).get("pipeline") or {}


# ---------- voiceink ----------

def voiceink_cases():
    res = []
    path = WORK / "modes.plist"
    modes = [{"id": "a", "name": "One", "isDefault": True, "selectedTranscriptionModelName": "parakeet-tdt-0.6b-v2"},
             {"id": "b", "name": "Two", "selectedTranscriptionModelName": "apple-speech"},
             {"id": "c", "name": "Three"}]
    for active, current, want in (("b", None, "apple-speech"), ("zz", None, "parakeet-tdt-0.6b-v2"),
                                  ("c", "parakeet-unified-0.6b", "parakeet-unified-0.6b")):
        prefs = {"activeConfigurationId": active, "modeConfigurationsV2": json.dumps(modes).encode()}
        if current:
            prefs["CurrentTranscriptionModel"] = current
        path.write_bytes(plistlib.dumps(prefs))
        os.environ["MEETING_NOTES_VOICEINK_PLIST"] = str(path)
        got = voiceink.settings()["model"]
        res.append(report(f"voiceink-mode-{active}", got == want, f"model={got}"))
    del os.environ["MEETING_NOTES_VOICEINK_PLIST"]

    found = voiceink.system_template(str(FAKE_BINARY))
    two = WORK / "VoiceInk-two"
    two.write_bytes(FAKE_TEMPLATE.encode() + b"\x00" + FAKE_TEMPLATE.replace("Fake", "Other").encode())
    res.append(report("voiceink-template", found == FAKE_TEMPLATE and voiceink.system_template(str(two)) is None
                      and voiceink.system_template(str(WORK / "missing")) is None))
    return res


# ---------- enhance ----------

def enhance_cases():
    res = []
    rec = text_rec("enh-skip")
    for name, e, want in (
            ("enhance-off", env("e0", plist("p0")), "off ([enhance] enabled = false)"),
            ("enhance-voiceink-off", env("e1", plist("p1", enhancement_on=False), enhance={"enabled": True}),
             "has AI enhancement off"),
            ("enhance-other-provider", env("e2", plist("p2", provider="Gemini"), enhance={"enabled": True}),
             "uses Gemini"),
            ("enhance-no-provider", env("e3", plist("p3", provider=None), enhance={"enabled": True}),
             "first connected provider"),
            ("enhance-no-template", env("e4", plist("p4", template=""), enhance={"enabled": True}), "template is empty")):
        rc, out = cli(e, "enhance", str(rec))
        res.append(report(name, rc == 5 and want in out and not (rec / "enhanced.md").exists(), out.strip()[-100:]))

    rec = text_rec("enh-arg")
    e = env("e5", plist("p5"), enhance={"enabled": True})
    STUB_LOG.unlink(missing_ok=True)
    rc, out = cli(e, "enhance", str(rec))
    calls = stub_calls()
    c = calls[0] if calls else {"argv": [], "env": {}, "stdin": "", "cwd": ""}
    system, user, full = (c["env"].get(k, "") for k in ("VOICEINK_SYSTEM_PROMPT", "VOICEINK_USER_PROMPT",
                                                        "VOICEINK_FULL_PROMPT"))
    body = (rec / "enhanced.md").read_text() if (rec / "enhanced.md").exists() else ""
    ok = (rc == 0 and len(calls) == 1 and c["argv"] == [full] and c["stdin"] == ""
          and system == FAKE_TEMPLATE.replace("%@", "Clean up the transcript.")
          and user == "\n<TRANSCRIPT>\n[00:01] System: um the supplier confirmed a delay\n"
                      "[00:05] Mic: please send the quote before Wednesday\n</TRANSCRIPT>"
          and "<SYSTEM_MESSAGE>" in full and "<USER_MESSAGE_PAYLOAD>" in full
          and os.path.realpath(c["cwd"]) != os.path.realpath(rec) and "The enhanced transcript." in body
          and oct((rec / "enhanced.md").stat().st_mode & 0o777) == "0o600")
    res.append(report("enhance-argument", ok, f"calls={len(calls)}"))
    st = pipeline_state(rec)
    rc, out = cli(e, "enhance", str(rec))
    res.append(report("enhance-skip", rc == 0 and "unchanged" in out and len(stub_calls()) == 1))
    (rec / "transcript.md").write_text("# Transcript: x\n\n---\n\n**[00:01] System:** a changed line\n")
    rc, out = cli(e, "enhance", str(rec))
    res.append(report("enhance-rerun", rc == 0 and len(stub_calls()) == 2 and "a changed line" in
                      stub_calls()[-1]["env"]["VOICEINK_USER_PROMPT"]))
    (rec / "enhanced.md").write_text(body + "my edit\n")
    rc, out = cli(e, "enhance", str(rec), "--force")
    res.append(report("enhance-hand-edit", rc == 4 and "edited by hand" in out))

    rec = text_rec("enh-stdin")
    STUB_LOG.unlink(missing_ok=True)
    rc, out = cli(env("e6", plist("p6", template=STDIN_TEMPLATE, system_instructions=False),
                      enhance={"enabled": True}), "enhance", str(rec))
    c = (stub_calls() or [{"stdin": "", "env": {}}])[0]
    res.append(report("enhance-stdin", rc == 0 and c["stdin"] == c["env"].get("VOICEINK_FULL_PROMPT")
                      and c["env"].get("VOICEINK_SYSTEM_PROMPT") == "Clean up the transcript."))

    rec = text_rec("enh-slow")
    rc, out = cli(dict(env("e7", plist("p7"), enhance={"enabled": True, "timeout_s": 2}), STUB_MODE="sleep"),
                  "enhance", str(rec))
    res.append(report("enhance-timeout", rc == 1 and "timed out" in out and not (rec / "enhanced.md").exists()))
    return res


# ---------- run, queue, egress (real transcription) ----------

def run_cases():
    models = pathlib.Path.home() / "Library/Application Support/FluidAudio/Models"
    if platform.system() != "Darwin" or not (pathlib.Path.home() / ".local/bin/meeting-asr").exists() \
            or not (models / "parakeet-unified-en-0.6b").exists():
        print("[run] SKIP (macOS with meeting-asr and the models only)")
        return [True]
    res = []
    root = WORK / "runs"
    root.mkdir()

    def recording(name):
        work = WORK / f"src-{name}"
        work.mkdir()
        rec = tt.make_recording(work)
        target = root / name
        rec.rename(target)
        return target

    base = {"paths": {"recordings": str(root)}, "run": {"auto_run": True}}
    plain = env("r0", plist("q0", enhancement_on=False), **base)
    rec = recording("plain")
    rc, out = cli(plain, "run", str(rec))
    st = pipeline_state(rec)
    res.append(report("run-transcribed", rc == 0 and st.get("state") == "transcribed"
                      and (st.get("enhancement") or "").startswith("skipped: off") and (rec / "transcript.md").exists(),
                      str(st)))

    enh = env("r1", plist("q1"), enhance={"enabled": True}, **base)
    rec = recording("enhanced")
    rc, out = cli(enh, "run", str(rec))
    res.append(report("run-enhanced", rc == 0 and pipeline_state(rec).get("state") == "enhanced"
                      and (rec / "enhanced.md").exists()))

    rec = recording("fails")
    rc, out = cli(dict(env("r2", plist("q2"), enhance={"enabled": True, "timeout_s": 2}, **base), STUB_MODE="sleep"),
                  "run", str(rec))
    st = pipeline_state(rec)
    res.append(report("run-failed", rc == 1 and st.get("state") == "failed" and "timed out" in (st.get("reason") or ""),
                      str(st)))

    off = env("r3", plist("q3"), paths={"recordings": str(root)})
    rc, out = cli(off, "run", str(rec), "--if-enabled")
    rc2, out2 = cli(off, "queue", "--if-enabled")
    res.append(report("run-if-enabled", rc == 5 and rc2 == 5))

    new = recording("new")
    stale = recording("stale")
    meta = json.loads((stale / "recording.json").read_text())
    meta["pipeline"] = {"state": "processing"}
    (stale / "recording.json").write_text(json.dumps(meta))
    rc, out = cli(plain, "queue")
    res.append(report("queue", rc == 0 and pipeline_state(new).get("state") == "transcribed"
                      and pipeline_state(stale).get("state") == "transcribed"
                      and pipeline_state(root / "fails").get("state") == "failed", out.strip().splitlines()[-1]))
    rc, out = cli(plain, "queue", "--retry")
    res.append(report("queue-retry", rc == 0 and pipeline_state(root / "fails").get("state") == "transcribed"))

    rec = recording("egress")
    e = env("r4", plist("q4", enhancement_on=False), transcribe={"no_network": False}, **base)
    rc, out = cli(e, "run", str(rec), sandbox=NO_NETWORK)  # sandboxes cannot nest, so the outer one covers all
    probe = subprocess.run(["/usr/bin/sandbox-exec", "-p", NO_NETWORK, "/usr/bin/python3", "-c",
                            "import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)"],
                           capture_output=True, text=True)
    res.append(report("egress", rc == 0 and pipeline_state(rec).get("state") == "transcribed" and probe.returncode != 0,
                      f"internet-blocked={probe.returncode != 0} {out.strip()[-120:] if rc else ''}"))
    return res


def config_case():
    """The committed example config parses and its keys are all known settings."""
    from meeting_notes.common import DEFAULTS, parse_toml_subset
    ex = parse_toml_subset((ROOT / "tools/meeting-notes/config.example.toml").read_text())
    unknown = [f"{s}.{k}" for s, v in ex.items() for k in v if k not in DEFAULTS.get(s, {})]
    return report("config-example", not unknown and ex["run"]["auto_run"] is False
                  and ex["enhance"]["enabled"] is False, f"unknown={unknown}")


if __name__ == "__main__":
    try:
        results = voiceink_cases() + enhance_cases() + run_cases() + [config_case()]
    finally:
        if "--keep" in sys.argv[1:]:
            print(f"kept: {WORK}")
        else:
            shutil.rmtree(WORK, ignore_errors=True)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    sys.exit(0 if all(results) else 1)
