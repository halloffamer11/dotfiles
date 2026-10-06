#!/usr/bin/env python3
"""Offline test of `meeting-notes transcribe` on a synthetic two-channel recording.

The recording is made with `say`: the mic channel is one voice (the user); the
system channel is two other voices taking turns; one system sentence is also
copied into the mic channel 15 dB lower (the mic hearing the speakers). VoiceInk's
settings come from a fake plist ($MEETING_NOTES_VOICEINK_PLIST). Checks:

  1. schema       <id>.json format_version 1 with the documented keys, and
                  <id>.md: header, "---", then "**[mm:ss] Speaker:** text"
  2. model        VoiceInk's selected model is the one used
  3. sources      the user's sentences are source=mic; the others source=system
  4. no-diarize   by default the system channel's speaker is just "system"
  5. echo         the copied sentence is dropped from the mic channel (dedup)
  6. fallback     a model this tool cannot run is skipped, with the reason kept,
                  and the next one that loads is used; VoiceInk's filler words apply
  6b. dictionary  VoiceInk's word replacements (a fake dictionary.store) change the
                  clean text and channel text, not the raw text
  7. override     [transcribe] model picks the model instead of VoiceInk
  8. diarize      diarize = true, max_speakers = 2: exactly S1 and S2 on system
  8b. short-merge the short-speaker rule on synthetic diarizer output (no models)
  9. skip         a rerun with unchanged fingerprints writes nothing
 10. rerun        a changed master.caf is transcribed again
 11. hand-edit    an edited <id>.json is never overwritten (exit 4)
 12. doctor       the model loads offline; a synced or group-readable folder fails

meeting-asr always runs with the network denied (the default no_network = true).
macOS only; skips (exit 0) when meeting-asr, ffmpeg or the models are missing.
Run:  make test-meeting-notes    (--keep leaves the work folder for inspection)
"""
import array, json, os, pathlib, platform, plistlib, shutil, sqlite3, subprocess, sys, tempfile

sys.dont_write_bytecode = True  # no __pycache__ under ~/.hammerspoon

ROOT = pathlib.Path(__file__).resolve().parents[3]
CLI = ROOT / "stow/hammerspoon/.hammerspoon/bin/meeting-notes"
ADAPTER = pathlib.Path.home() / ".local/bin/meeting-asr"
MODELS = pathlib.Path.home() / "Library/Application Support/FluidAudio/Models"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
RATE = 48000
GAP = 1.2  # silence between turns, seconds

USER = "Fred"
SYSTEM = ("Samantha", "Daniel")
TURNS = [  # (voice, text, channel)
    ("Samantha", "Good morning everyone. Let us start with the schedule for the bracket design review.", "system"),
    ("Daniel", "The structural model is about eighty percent complete and the load cases are due on Friday.", "system"),
    (USER, "I can review the load cases on Friday afternoon and send comments the same day.", "mic"),
    ("Samantha", "Good. The supplier confirmed a two week delay on the bracket parts this morning.", "system"),
    ("Daniel", "We could qualify a second supplier, but that option costs more money.", "system"),
    (USER, "Please send me the quote from the second supplier before Wednesday.", "mic"),
    ("Samantha", "I will ask them today and forward the numbers when they reply.", "system"),
]
ECHO_TURN = 4  # this system turn is also heard by the mic, 15 dB lower


def skip(why):
    print(f"SKIP: {why}")
    sys.exit(0)


def speak(voice, text, work, i):
    aiff, raw = work / f"t{i}.aiff", work / f"t{i}.f32"
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", str(aiff), "-ar", str(RATE), "-ac", "1",
                    "-f", "f32le", str(raw)], check=True)
    a = array.array("f")
    a.frombytes(raw.read_bytes())
    return a


def make_recording(work):
    rec = work / "meeting-2026-01-01-000000"
    rec.mkdir(mode=0o700)
    clips = [speak(v, t, work, i) for i, (v, t, _) in enumerate(TURNS)]
    total = sum(len(c) for c in clips) + int(GAP * RATE) * (len(clips) + 1)
    mic, sysc = array.array("f", [0.0]) * total, array.array("f", [0.0]) * total
    pos = int(GAP * RATE)
    for i, (clip, (_, _, ch)) in enumerate(zip(clips, TURNS)):
        target = mic if ch == "mic" else sysc
        target[pos:pos + len(clip)] = clip
        if i == ECHO_TURN:
            mic[pos:pos + len(clip)] = array.array("f", (x * 0.18 for x in clip))  # about -15 dB
        pos += len(clip) + int(GAP * RATE)
    (work / "mic.f32").write_bytes(mic.tobytes())
    (work / "sys.f32").write_bytes(sysc.tobytes())
    write_master(work, rec)
    (rec / "recording.json").write_text(json.dumps({
        "format_version": 1, "id": rec.name, "layout": "mic-system-2ch", "channels": {"0": "mic", "1": "system"},
        "state": "recorded", "legs": {"mic": {"present": True}, "system": {"present": True}}}))
    return rec


def write_master(work, rec, extra=""):
    subprocess.run([FFMPEG, "-loglevel", "error", "-y",
                    "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", str(work / "mic.f32"),
                    "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", str(work / "sys.f32"),
                    "-filter_complex", "[0:a][1:a]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR" + extra + "[m]",
                    "-map", "[m]", "-c:a", "pcm_f32le", "-f", "caf", str(rec / "master.caf")], check=True)


def voiceink_plist(path, model, fillers=None, formatting=True, enhancement=None):
    """A fake VoiceInk preferences file with one active mode."""
    mode = {"id": "mode-1", "name": "Dictation", "isDefault": True, "selectedTranscriptionModelName": model,
            "selectedLanguage": "en", "isTextFormattingEnabled": formatting, "isAIEnhancementEnabled": False,
            "selectedPrompt": "prompt-1"}
    prefs = {"activeConfigurationId": "mode-1",
             "customPrompts": json.dumps([{"id": "prompt-1", "title": "Default", "useSystemInstructions": True,
                                           "promptText": "Clean up the transcript."}]).encode()}
    if fillers is not None:
        prefs["FillerWords"] = fillers
    if enhancement:
        mode.update(enhancement.pop("mode", {}))
        prefs.update(enhancement)
    prefs["modeConfigurationsV2"] = json.dumps([mode]).encode()
    path.write_bytes(plistlib.dumps(prefs))
    return str(path)


def voiceink_dictionary(path, rules=()):
    """A fake VoiceInk dictionary.store with ZWORDREPLACEMENT rows (original, replacement)."""
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE ZWORDREPLACEMENT (Z_PK INTEGER PRIMARY KEY, Z_ENT INTEGER, Z_OPT INTEGER, "
                "ZISENABLED INTEGER, ZDATEADDED TIMESTAMP, ZORIGINALTEXT VARCHAR, ZREPLACEMENTTEXT VARCHAR, ZID BLOB)")
    for i, (o, r) in enumerate(rules):
        con.execute("INSERT INTO ZWORDREPLACEMENT VALUES (?, 1, 1, 1, ?, ?, ?, ?)", (i + 1, float(i), o, r, bytes([i])))
    con.commit()
    con.close()
    return str(path)


def run(rec, env, *extra):
    r = subprocess.run([str(CLI), "transcribe", str(rec), *extra], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def words(text):
    return {w.strip(".,?!").lower() for w in text.split()}


def short_merge_case():
    """A 2 s third speaker joins the speaker with the most similar embedding."""
    sys.path.insert(0, str(CLI.parent.parent))
    from meeting_notes import transcribe as mn
    a, b, c = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.1, 0.9, 0.1]
    diar = [{"speaker": "A", "start": 0, "end": 6, "embedding": a}, {"speaker": "B", "start": 6, "end": 12, "embedding": b},
            {"speaker": "C", "start": 12, "end": 14, "embedding": c}]
    out, merges = mn.merge_short_speakers(diar, 3.0)
    by_time, _ = mn.merge_short_speakers([dict(s, embedding=[]) for s in diar], 3.0)
    return report("short-merge", [s["speaker"] for s in out] == ["A", "B", "B"] and merges[0]["by"] == "embedding"
                  and [s["speaker"] for s in by_time] == ["A", "B", "B"], f"merges={merges}")


def report(name, ok, detail=""):
    print(f"[{name}] {'PASS' if ok else 'FAIL'} {detail}".rstrip())
    return ok


def main():
    if platform.system() != "Darwin":
        skip("macOS only")
    for p, what in ((ADAPTER, "meeting-asr (make meeting-notes)"), (pathlib.Path(FFMPEG), "ffmpeg"),
                    (MODELS / "parakeet-unified-en-0.6b", "the Parakeet Unified model"),
                    (MODELS / "parakeet-tdt-0.6b-v2-coreml", "the Parakeet v2 model"),
                    (MODELS / "speaker-diarization", "the diarizer model")):
        if not p.exists():
            skip(f"{what} not found at {p}")
    work = pathlib.Path(tempfile.mkdtemp(prefix="mn-test."))

    def env_for(name, vi_model="parakeet-unified-0.6b", fillers=None, rules=(), **transcribe):
        cfg = work / f"{name}.toml"
        lines = [f'[paths]\nrecordings = "{work}"\n[transcribe]\nno_network = true']
        lines += [f"{k} = {json.dumps(v)}" for k, v in transcribe.items()]
        cfg.write_text("\n".join(lines) + "\n")
        return dict(os.environ, MEETING_NOTES_CONFIG=str(cfg),
                    MEETING_NOTES_VOICEINK_PLIST=voiceink_plist(work / f"{name}.plist", vi_model, fillers),
                    MEETING_NOTES_VOICEINK_DICTIONARY=voiceink_dictionary(work / f"{name}.store", rules))

    def fresh(rec):
        for f in (f"{rec.name}.json", f"{rec.name}.md", ".meeting-notes-state.json"):
            (rec / f).unlink(missing_ok=True)

    results = []
    try:
        rec = make_recording(work)
        env = env_for("default")
        rc, out = run(rec, env)
        if rc != 0:
            print(out)
            return report("transcribe", False, f"rc={rc}")
        t = json.loads((rec / f"{rec.name}.json").read_text())
        md = (rec / f"{rec.name}.md").read_text()
        lines = [l for l in md.split("\n---\n", 1)[1].splitlines() if l.strip()]
        keys = {"format_version", "recording_id", "recorded", "model", "voiceink_postprocessing", "diarize",
                "fingerprints", "channels", "speakers", "segments", "merges", "dedup", "assumptions"}
        seg_keys = {"id", "start", "end", "source", "speaker", "text", "text_clean", "words"}
        results.append(report("schema", t["format_version"] == 1 and keys <= t.keys()
                              and all(seg_keys <= s.keys() for s in t["segments"])
                              and t["channels"]["mic"]["role"].startswith("microphone")
                              and md.startswith("# Transcript: ") and "- Model: parakeet-unified-0.6b" in md
                              and len(lines) == len(t["segments"]) and lines[0].startswith("**[00:0")
                              and all(":** " in l for l in lines), f"{len(t['segments'])} segments"))
        results.append(report("model", t["model"]["used"] == "parakeet-unified-0.6b"
                              and t["model"]["tried"][0]["role"] == "VoiceInk's selected model", str(t["model"]["used"])))

        mic_text = " ".join(s["text"] for s in t["segments"] if s["source"] == "mic")
        sys_text = " ".join(s["text"] for s in t["segments"] if s["source"] == "system")
        user_words = words(TURNS[2][1]) | words(TURNS[5][1])
        sys_only = words(TURNS[0][1]) | words(TURNS[3][1])
        mic_ok = len(user_words & words(mic_text)) / len(user_words) > 0.7 and not (words(TURNS[0][1]) <= words(mic_text))
        sys_ok = len(sys_only & words(sys_text)) / len(sys_only) > 0.8
        results.append(report("sources", mic_ok and sys_ok and all(s["speaker"] == "mic" for s in t["segments"]
                                                                    if s["source"] == "mic")))
        sys_speakers = sorted({s["speaker"] for s in t["segments"] if s["source"] == "system"})
        results.append(report("no-diarize", sys_speakers == ["system"] and not t["diarize"]["on"], str(sys_speakers)))
        echo = words(TURNS[ECHO_TURN][1])
        echo_in_mic = len(echo & words(mic_text) - user_words) / len(echo)
        results.append(report("echo", any(d["kept"] == "system" for d in t["dedup"]) and echo_in_mic < 0.3,
                              f"dedup={t['dedup']} echo-words-left-in-mic={echo_in_mic:.2f}"))

        before = (rec / f"{rec.name}.json").stat().st_mtime_ns
        rc, out = run(rec, env)
        results.append(report("skip", rc == 0 and "unchanged" in out
                              and (rec / f"{rec.name}.json").stat().st_mtime_ns == before))

        fresh(rec)
        rc, out = run(rec, env_for("fallback", vi_model="some-cloud-model", fillers=["bracket"]))
        t2 = json.loads((rec / f"{rec.name}.json").read_text()) if rc == 0 else {}
        tried = t2.get("model", {}).get("tried", [])
        no_bracket = all("bracket" not in s["text_clean"].lower() for s in t2.get("segments", []))
        raw_bracket = any("bracket" in s["text"].lower() for s in t2.get("segments", []))
        results.append(report("fallback", rc == 0 and tried[0]["model"] == "some-cloud-model" and "skipped" in tried[0]
                              and t2["model"]["used"] == "parakeet-unified-0.6b" and no_bracket and raw_bracket,
                              f"tried={tried}"))

        fresh(rec)
        rc, out = run(rec, env_for("dictionary", rules=[("supplier, suppliers", "Vendor"), ("Friday", "FRI")]))
        t7 = json.loads((rec / f"{rec.name}.json").read_text()) if rc == 0 else {}
        segs = t7.get("segments", [])
        clean_text = " ".join(s["text_clean"] for s in segs)
        raw_text = " ".join(s["text"] for s in segs)
        results.append(report("dictionary", rc == 0 and "Vendor" in clean_text and "FRI" in clean_text
                              and "supplier" not in clean_text.lower() and "supplier" in raw_text.lower()
                              and "Vendor" in (t7["channels"]["system"]["text"] or "")
                              and t7["voiceink_postprocessing"]["word_replacements"] == 2, out.strip()[-120:]))

        fresh(rec)
        rc, out = run(rec, env_for("override", vi_model="whisper-cloud-x", model="parakeet-tdt-0.6b-v2"))
        t3 = json.loads((rec / f"{rec.name}.json").read_text()) if rc == 0 else {}
        results.append(report("override", rc == 0 and t3["model"]["used"] == "parakeet-tdt-0.6b-v2"
                              and t3["model"]["tried"][0]["role"] == "config override", out.strip()[-120:]))

        fresh(rec)
        rc, out = run(rec, env_for("diarize", diarize=True, max_speakers=2, model="parakeet-tdt-0.6b-v2"))
        t4 = json.loads((rec / f"{rec.name}.json").read_text()) if rc == 0 else {}
        sys_speakers = sorted({s["speaker"] for s in t4.get("segments", []) if s["source"] == "system"})
        results.append(short_merge_case())
        results.append(report("diarize", sys_speakers == ["S1", "S2"], f"system speakers={sys_speakers}"))

        fresh(rec)
        rc, out = run(rec, env)
        t5 = json.loads((rec / f"{rec.name}.json").read_text())
        write_master(work, rec, extra=",volume=0.9")
        rc, out = run(rec, env)
        t6 = json.loads((rec / f"{rec.name}.json").read_text())
        results.append(report("rerun", rc == 0 and t6["fingerprints"]["audio_sha256"] != t5["fingerprints"]["audio_sha256"]))

        (rec / f"{rec.name}.json").write_text((rec / f"{rec.name}.json").read_text().replace("Friday", "Thursday"))
        rc, out = run(rec, env, "--force")
        results.append(report("hand-edit", rc == 4 and "edited by hand" in out))

        synced = work / "Library/CloudStorage/Drive/Recordings"
        synced.mkdir(parents=True, mode=0o755)
        bad = work / "bad.toml"
        bad.write_text(f'[paths]\nrecordings = "{synced}"\n')
        r = subprocess.run([str(CLI), "doctor"], capture_output=True, text=True,
                           env=dict(env, MEETING_NOTES_CONFIG=str(bad)))
        loads = "parakeet-unified-0.6b loads offline" in r.stdout
        flags = "FAIL  output folder" in r.stdout and "synced" in r.stdout and "mode 0o755" in r.stdout
        results.append(report("doctor", r.returncode == 1 and loads and flags, r.stdout.strip()[-200:] if not loads else ""))
    finally:
        if "--keep" in sys.argv[1:]:
            print(f"kept: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
