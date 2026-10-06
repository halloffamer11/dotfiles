"""transcribe: master.caf (or the stereo listen.m4a) -> transcript.json + transcript.md, offline, the way
VoiceInk transcribes a file dragged onto it.

Model: VoiceInk's selected model (voiceink.py), or [transcribe] model in
config.toml. When it cannot run offline here (a cloud model, a model this tool
does not support, or missing files), the next of voiceink.FALLBACKS that loads
is used; transcript.json "model" records what was asked for, what was used, and
why each skipped one was skipped. Every meeting-asr call runs in a no-network
sandbox (no_network = true).

Per channel (ch0 = mic, ch1 = system), like VoiceInk's file path:
speech-to-text, then VoiceInk's output filter (<TAG>...</TAG> blocks, [..] (..)
{..} and its filler words removed), then paragraphs when the VoiceInk mode has
text formatting on, then the word replacements from VoiceInk's dictionary.
Not mirrored: VoiceInk's VAD setting.

  channels   per channel: role, transcribed, duration, text_raw, text
  segments   start, end, source (mic|system), speaker, text (raw), text_clean,
             words. speaker is the channel name ("mic" or "system"), or S1, S2, ...
             on the system channel with diarize = true (off by default, as in
             VoiceInk). mic = the user is an assumption (the mic also hears the
             room and the speakers). An engine without word timings (Apple Speech)
             gives one segment per channel.
  merges     (diarize) a diarized speaker with less than min_speaker_s of speech
             joins the speaker whose mean embedding is most similar (cosine).
             max_speakers (an upper bound) catches a voice split into two long
             clusters, which this rule does not.
  dedup      echo rule: a run of at least echo_min_words consecutive mic words
             that each match a system word (same normalized text, start within
             0.5 s; one unmatched word may sit inside the run) is speech the mic
             heard from the speakers. The system copy is kept and the mic run
             dropped; only when the system copy is weaker (mean word confidence
             lower by more than 0.1) is the mic run kept instead, as source=mic
             with echo_of_system=true, and the system words dropped.
  fingerprints  sha256 of listen.m4a (master.caf when there is none), the model used (and a manifest hash of its
             folder), the adapter and FluidAudio versions, and the settings.
             Unchanged fingerprints: the run is skipped.

transcript.md: a short header (recording, recorded times, model, channel roles),
a "---" rule, then the segments in time order, one paragraph each:
"**[mm:ss] Speaker:** text".
"""
import json, math, os, platform, re, subprocess, tempfile, time

from . import voiceink
from .common import (FFMPEG, FORMAT_VERSION, adapter, audio_source, probe, guard, manifest, now_iso, read_recording, record_output,
                     recording_lock, sha256_file, sha256_text, write_json, write_text)


def norm(word):
    return re.sub(r"[^a-z0-9']", "", word.lower())


def clean(text, fillers):
    """VoiceInk's TranscriptionOutputFilter: drop <TAG>...</TAG> blocks and bracketed
    text, then each filler word (\\b<word>\\b[,.]? case-insensitive), then squeeze spaces."""
    text = re.sub(r"<([A-Za-z][A-Za-z0-9:_-]*)[^>]*>[\s\S]*?</\1>", "", text)
    for pattern in (r"\[.*?\]", r"\(.*?\)", r"\{.*?\}"):
        text = re.sub(pattern, "", text)
    for w in fillers:
        text = re.sub(r"\b" + re.escape(w) + r"\b[,.]?", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip()


def mmss(t):
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def choose_model(cfg, vi):
    """(name, adapter args, log) of the first candidate that loads offline."""
    root = cfg["models"]["models_root"]
    log = []
    for name, why in voiceink.candidates(vi["model"], cfg["transcribe"]["model"] or None):
        ok, reason = voiceink.model_files_ok(name, root)
        if not ok:
            log.append({"model": name, "role": why, "skipped": reason})
            continue
        args = voiceink.adapter_args(name, vi["language"], root)
        try:
            adapter(cfg, "check", *args)
        except RuntimeError as e:
            log.append({"model": name, "role": why, "skipped": str(e)[-200:]})
            continue
        log.append({"model": name, "role": why, "used": True})
        return name, args, log
    raise RuntimeError("no transcription model loads offline: " + "; ".join(
        f"{l['model']}: {l['skipped']}" for l in log))


def model_fingerprint(name, cfg):
    spec = voiceink.ENGINES[name]
    if spec["engine"] == "apple":
        return {"name": name, "os": platform.mac_ver()[0]}
    return {"name": name, **manifest(os.path.join(cfg["models"]["models_root"], spec["folder"]))}


def cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def mean(vectors):
    return [sum(c) / len(vectors) for c in zip(*vectors)] if vectors else []


# ---------- merging ----------

def merge_short_speakers(diar, min_s):
    """Fold every speaker with less than min_s of speech into the most similar other
    speaker (cosine of mean embeddings). Returns (segments, merges)."""
    merges = []
    while True:
        total = {}
        for s in diar:
            total[s["speaker"]] = total.get(s["speaker"], 0) + s["end"] - s["start"]
        if len(total) < 2:
            return diar, merges
        short = min(total, key=total.get)
        if total[short] >= min_s:
            return diar, merges
        centroid = {sp: mean([s["embedding"] for s in diar if s["speaker"] == sp and s.get("embedding")])
                    for sp in total}
        others = [sp for sp in total if sp != short]
        if centroid[short]:
            sims = {sp: cosine(centroid[short], centroid[sp]) for sp in others if centroid[sp]}
        else:
            sims = {}
        if sims:
            into, how = max(sims, key=sims.get), "embedding"
        else:  # no embeddings: nearest neighbour in time
            mid = sum((s["start"] + s["end"]) / 2 for s in diar if s["speaker"] == short)
            into = min(others, key=lambda sp: min(abs((s["start"] + s["end"]) / 2 - mid)
                                                  for s in diar if s["speaker"] == sp))
            how = "time"
        merges.append({"from_diarizer_id": short, "into": into, "speech_s": round(total[short], 2), "by": how,
                       "similarity": round(sims[into], 3) if sims else None})
        for s in diar:
            if s["speaker"] == short:
                s["speaker"] = into


def speaker_at(diar, w):
    """The diarized speaker that overlaps the word most, else the nearest segment."""
    best, best_ov = None, 0.0
    for s in diar:
        ov = min(w["e"], s["end"]) - max(w["s"], s["start"])
        if ov > best_ov:
            best, best_ov = s["speaker"], ov
    if best is None and diar:
        mid = (w["s"] + w["e"]) / 2
        best = min(diar, key=lambda s: min(abs(mid - s["start"]), abs(mid - s["end"])))["speaker"]
    return best


def group(words, source, speaker_of, pause_s, fillers):
    """Consecutive words become one segment until the speaker changes or a pause."""
    segs = []
    for w in words:
        sp = speaker_of(w)
        if segs and segs[-1]["speaker"] == sp and w["s"] - segs[-1]["end"] <= pause_s \
                and segs[-1]["words"][-1].get("echo") == w.get("echo"):
            segs[-1]["words"].append(w)
            segs[-1]["end"] = w["e"]
        else:
            segs.append({"source": source, "speaker": sp, "start": w["s"], "end": w["e"], "words": [w]})
    for s in segs:
        s["text"] = " ".join(w["w"] for w in s["words"])
        s["text_clean"] = clean(s["text"], fillers)
        s["confidence"] = round(sum(w["c"] for w in s["words"]) / len(s["words"]), 4)
        if s["words"][0].get("echo"):
            s["echo_of_system"] = True
        for w in s["words"]:
            w.pop("echo", None)
    return segs


def dedup(mic_words, sys_words, min_words):
    """Drop speech the mic heard from the speakers (see the module docstring)."""
    def match(w):
        n = norm(w["w"])
        return next((i for i, x in enumerate(sys_words) if n and n == norm(x["w"]) and abs(w["s"] - x["s"]) <= 0.5),
                    None)
    hits = [match(w) for w in mic_words]
    runs, i = [], 0
    while i < len(mic_words):
        if hits[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < len(mic_words) and (hits[j + 1] is not None or
                                          (j + 2 < len(mic_words) and hits[j + 2] is not None)):
            j += 1
        if sum(h is not None for h in hits[i:j + 1]) >= min_words:
            runs.append((i, j))
        i = j + 1
    drop_mic, drop_sys, log = set(), set(), []
    for i, j in runs:
        sys_idx = {h for h in hits[i:j + 1] if h is not None}
        mic_c = sum(w["c"] for w in mic_words[i:j + 1]) / (j - i + 1)
        sys_c = sum(sys_words[k]["c"] for k in sys_idx) / len(sys_idx)
        entry = {"start": round(mic_words[i]["s"], 2), "end": round(mic_words[j]["e"], 2), "words": j - i + 1,
                 "mic_confidence": round(mic_c, 4), "system_confidence": round(sys_c, 4)}
        if sys_c < mic_c - 0.1:
            drop_sys |= sys_idx
            for w in mic_words[i:j + 1]:
                w["echo"] = True
            entry["kept"] = "mic"
        else:
            drop_mic |= set(range(i, j + 1))
            entry["kept"] = "system"
        log.append(entry)
    return ([w for k, w in enumerate(mic_words) if k not in drop_mic],
            [w for k, w in enumerate(sys_words) if k not in drop_sys], log)


def markdown(t):
    label = {"mic": "Mic", "system": "System"}
    rec, m = t["recorded"], t["model"]
    when = f"{rec['start']} to {rec['end']}" if rec.get("start") else "unknown"
    dur = f" ({rec['duration_s']:.0f} s)" if rec.get("duration_s") else ""
    head = [f"# Transcript: {t['recording_id']}", "",
            f"- Recorded: {when}{dur}" + ("" if rec.get("state") != "partial" else "; partial: a capture leg is missing"),
            f"- Model: {m['used']}" + (f" (VoiceInk selected {m['voiceink_selected']})"
                                         if m["voiceink_selected"] and m["voiceink_selected"] != m["used"] else
                                         " (VoiceInk's selection)" if m["voiceink_selected"] else ""),
            f"- Mic: {t['channels']['mic']['role']}; System: {t['channels']['system']['role']}",
            "", "---", ""]
    body = [f"**[{mmss(s['start'])}] {label.get(s['speaker'], s['speaker'])}:** {s['text_clean']}\n"
            for s in t["segments"] if s["text_clean"]]
    return "\n".join(head + body)


def run(rec, cfg, force=False):
    """Returns (path, "written" | "unchanged"). Raises Refused, Busy, RuntimeError."""
    with recording_lock(rec):
        meta = read_recording(rec)
        src = audio_source(rec)
        listen = os.path.join(rec, "listen.m4a")
        out = os.path.join(rec, "transcript.json")
        t = cfg["transcribe"]
        vi = voiceink.settings()
        fillers = vi["filler_words"]
        rules, dict_error = voiceink.word_replacements()
        name, args, model_log = choose_model(cfg, vi)
        version = adapter(cfg, "version")
        diarize = bool(t["diarize"])
        fingerprints = {
            "audio_sha256": sha256_file(listen if os.path.exists(listen) else src),
            "model": model_fingerprint(name, cfg),
            "diarizer_model": manifest(os.path.join(cfg["models"]["models_root"], cfg["models"]["diarizer_folder"]))
            if diarize else None,
            "fluidaudio": version["sdk"], "adapter": version["adapter"],
            "settings_sha256": sha256_text(json.dumps(
                {"transcribe": t, "language": vi["language"], "formatting": vi["text_formatting"],
                 "fillers": fillers, "replacements": rules}, sort_keys=True)),
        }
        if guard(rec, "transcript", out, fingerprints, force) == "unchanged":
            remove_master(rec, cfg)
            return out, "unchanged"

        present = {n: meta["legs"][n]["present"] for n in ("mic", "system")}
        began = time.time()
        results = {}
        with tempfile.TemporaryDirectory(prefix="meeting-notes.") as tmp:
            for chan, ch in (("mic", 0), ("system", 1)):
                if not present[chan]:
                    continue
                wav = os.path.join(tmp, f"{chan}.wav")
                subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", src,
                                "-af", f"pan=mono|c0=c{ch}", "-ar", "16000", wav], check=True)
                results[chan] = {"asr": adapter(cfg, "transcribe", *args, wav)}
                if chan == "system" and diarize and results[chan]["asr"]["words"]:
                    extra = (["--num-speakers", str(t["num_speakers"])] if t["num_speakers"] else
                             ["--max-speakers", str(t["max_speakers"])] if t["max_speakers"] else [])
                    try:
                        results[chan]["diar"] = adapter(cfg, "diarize", "--models-root",
                                                        cfg["models"]["models_root"], *extra, wav)
                    except RuntimeError as e:
                        if "noSpeechDetected" not in str(e):
                            raise
                        results[chan]["diar"] = {"segments": []}

        timed = all(results[c]["asr"]["words"] or not results[c]["asr"]["text"].strip() for c in results)
        merges, dedup_log = [], []
        if timed:
            mic_words = results["mic"]["asr"]["words"] if "mic" in results else []
            sys_words = results["system"]["asr"]["words"] if "system" in results else []
            mic_words, sys_words, dedup_log = dedup(mic_words, sys_words, t["echo_min_words"])
            speaker_of = lambda w: "system"
            if "diar" in results.get("system", {}) and results["system"]["diar"]["segments"]:
                diar, merges = merge_short_speakers(results["system"]["diar"]["segments"], t["min_speaker_s"])
                order = []
                for s in sorted(diar, key=lambda s: s["start"]):
                    if s["speaker"] not in order:
                        order.append(s["speaker"])
                names = {sp: f"S{i + 1}" for i, sp in enumerate(order)}
                for m in merges:
                    m["into"] = names.get(m["into"], m["into"])
                speaker_of = lambda w: names.get(speaker_at(diar, w), "S?")
            segments = group(sys_words, "system", speaker_of, t["pause_s"], fillers) + \
                group(mic_words, "mic", lambda w: "mic", t["pause_s"], fillers)
        else:  # no word timings (Apple Speech): one segment per channel
            segments = [{"source": c, "speaker": c, "start": 0.0, "end": results[c]["asr"]["duration_s"],
                         "text": results[c]["asr"]["text"], "text_clean": clean(results[c]["asr"]["text"], fillers),
                         "confidence": None, "words": []} for c in results if results[c]["asr"]["text"].strip()]

        segments.sort(key=lambda s: (s["start"], s["source"]))
        for s in segments:
            s["text_clean"] = voiceink.replace_words(s["text_clean"], rules)
        for i, s in enumerate(segments):
            s["id"] = i + 1
            s["start"], s["end"] = round(s["start"], 3), round(s["end"], 3)
        speakers = {}
        for s in segments:
            sp = speakers.setdefault(s["speaker"], {"id": s["speaker"], "source": s["source"], "speech_s": 0.0})
            sp["speech_s"] = round(sp["speech_s"] + s["end"] - s["start"], 2)

        channels = {}
        for c, role in (("mic", "microphone (assumed to be the user)"), ("system", "system audio (the other side)")):
            r = results.get(c, {}).get("asr")
            text = clean(r["text"], fillers) if r else None
            if text and vi["text_formatting"]:
                text = adapter(cfg, "format", stdin=text)["text"]
            if text:
                text = voiceink.replace_words(text, rules)
            channels[c] = {"role": role, "transcribed": r is not None,
                           "duration_s": round(r["duration_s"], 3) if r else None,
                           "processing_s": round(r["processing_s"], 3) if r else None,
                           "text_raw": r["text"] if r else None, "text": text}

        transcript = {
            "format_version": FORMAT_VERSION,
            "recording_id": meta.get("id"),
            "generated_at": now_iso(),
            "processing_s": round(time.time() - began, 2),
            "recorded": {"start": (meta.get("actual") or {}).get("start"), "end": (meta.get("actual") or {}).get("end"),
                         "duration_s": (meta.get("actual") or {}).get("duration_s"), "state": meta.get("state")},
            "model": {"voiceink_selected": vi["model"], "voiceink_mode": vi["mode"], "used": name,
                      "engine": voiceink.ENGINES[name]["engine"], "language": vi["language"], "tried": model_log,
                      "word_timings": timed},
            "voiceink_postprocessing": {"filler_words": fillers, "paragraphs": vi["text_formatting"],
                                        "word_replacements": len(rules), "dictionary_error": dict_error,
                                        "not_mirrored": ["VAD"]},
            "diarize": {"on": diarize, "max_speakers": t["max_speakers"] or None,
                        "num_speakers": t["num_speakers"] or None},
            "fingerprints": fingerprints,
            "channels": channels,
            "speakers": sorted(speakers.values(), key=lambda s: (s["source"], s["id"])),
            "merges": merges,
            "dedup": dedup_log,
            "assumptions": ["Speaker 'mic' is assumed to be the user; the mic also hears the room and the speakers."],
            "segments": [{k: s[k] for k in ("id", "start", "end", "source", "speaker", "text", "text_clean",
                                            "confidence", "words")}
                         | ({"echo_of_system": True} if s.get("echo_of_system") else {}) for s in segments],
        }
        write_text(os.path.join(rec, "transcript.md"), markdown(transcript))
        write_json(out, transcript)
        record_output(rec, "transcript", out, fingerprints)
        remove_master(rec, cfg)
        return out, "written"


# The recorder's listen.m4a chain (record-meeting-finalize): mic left +6 dB, system
# right, limiter, 256k AAC.
STEREO_LISTEN = ("[0:a]channelsplit=channel_layout=stereo[m][s];[m]volume=6dB,alimiter=limit=0.97[mv];"
                 "[s]alimiter=limit=0.97[sv];[mv][sv]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR[o]")


def remove_master(rec, cfg):
    """Once a transcript exists, master.caf (about 1.4 GB an hour) goes; the stereo
    listen.m4a keeps both channels for playback and for a later rerun. A recording
    made before listen.m4a was stereo gets a stereo listen.m4a from master.caf
    first. Kept when [transcribe] keep_master = true, or when listen.m4a does not
    come out stereo and as long as master.caf."""
    master, listen = os.path.join(rec, "master.caf"), os.path.join(rec, "listen.m4a")
    if cfg["transcribe"]["keep_master"] or not os.path.exists(master):
        return False
    pm = probe(master)
    pl = probe(listen) if os.path.exists(listen) else None
    if pm and pm[0] == 2 and not (pl and pl[0] == 2):
        tmp = listen + ".tmp"
        r = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", master,
                            "-filter_complex", STEREO_LISTEN, "-map", "[o]", "-c:a", "aac", "-b:a", "256k",
                            "-f", "mp4", tmp])
        pt = probe(tmp) if r.returncode == 0 else None
        if not (pt and pt[0] == 2 and abs(pt[2] - pm[2]) <= 0.5):
            if os.path.exists(tmp):
                os.remove(tmp)
            return False
        os.chmod(tmp, 0o600)
        os.replace(tmp, listen)
        pl = pt
    if not (pm and pl and pl[0] == 2 and abs(pl[2] - pm[2]) <= 0.5):
        return False
    os.remove(master)
    path = os.path.join(rec, "recording.json")
    meta = json.load(open(path))
    meta.setdefault("files", {})["master"] = None
    meta["master_removed"] = {"at": now_iso(), "reason": "transcribed; listen.m4a holds both channels"}
    write_json(path, meta)
    return True
