"""transcribe: master.caf -> transcript.json (format_version 1), offline.

Splits master.caf (ch0 = mic, ch1 = system) to 16 kHz mono, runs meeting-asr
(the FluidAudio adapter) per channel and diarization on the system channel.
Every meeting-asr call runs in a no-network sandbox (no_network = true).

  segments   start, end, source (mic|system), speaker, text (raw ASR), text_clean
             (filler words removed: VoiceInk's default list and regex), words
  speakers   system speakers S1, S2, ... in order of first speech; the mic
             channel's speaker is "mic". mic = the user is an ASSUMPTION (the mic
             also hears the room and the speakers), listed under assumptions.
  merges     short-speaker rule: a diarized speaker with less than min_speaker_s
             of speech in total joins the speaker whose mean embedding is most
             similar (cosine), instead of becoming a new speaker. It does not
             catch a voice split into two long clusters; max_speakers (an upper
             bound) does. When match found the meeting, its invitee count + 1
             is the bound, unless max_speakers or num_speakers is set.
  dedup      echo rule: a run of at least echo_min_words consecutive mic words
             that each match a system word (same normalized text, start within
             0.5 s; one unmatched word may sit inside the run) is speech the mic
             heard from the speakers. The system copy is kept and the mic run
             dropped; only when the system copy is weaker (mean word confidence
             lower by more than 0.1) is the mic run kept instead, as source=mic
             with echo_of_system=true, and the system words dropped.
  fingerprints  sha256 of master.caf, a manifest hash of each model folder, the
             FluidAudio and adapter versions, and the settings (with the
             effective speaker bound). Unchanged fingerprints: the run is skipped.
"""
import json, os, re, math, subprocess, tempfile, time

from .common import (FFMPEG, FORMAT_VERSION, adapter, guard, manifest, now_iso, read_recording, record_output,
                     recording_lock, sha256_file, sha256_text, write_json)

# VoiceInk FillerWordManager.defaultFillerWords (Beingpax/VoiceInk, read 2026-10-05)
FILLER_WORDS = ["uh", "um", "uhm", "umm", "uhh", "uhhh", "hmm", "hm", "mmm", "mm", "mh", "ehh"]


def norm(word):
    return re.sub(r"[^a-z0-9']", "", word.lower())


def clean(text):
    """VoiceInk's filler filter: \\b<word>\\b[,.]? case-insensitive, then squeeze spaces."""
    for w in FILLER_WORDS:
        text = re.sub(r"\b" + re.escape(w) + r"\b[,.]?", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip()


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


def group(words, source, speaker_of, pause_s):
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
        s["text_clean"] = clean(s["text"])
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


def speaker_bound(rec, t):
    """max_speakers from settings, else the matched meeting's invitees + 1, else none."""
    if t["max_speakers"]:
        return int(t["max_speakers"]), "settings"
    path = os.path.join(rec, "meeting.json")
    if os.path.exists(path):
        m = json.load(open(path))
        if m.get("state") == "matched" and m["event"].get("invitee_count"):
            return m["event"]["invitee_count"] + 1, "meeting.json invitees + 1"
    return 0, None


def run(rec, cfg, force=False):
    """Returns (path, "written" | "unchanged"). Raises Refused, Busy, RuntimeError."""
    with recording_lock(rec):
        meta = read_recording(rec)
        master = os.path.join(rec, "master.caf")
        out = os.path.join(rec, "transcript.json")
        bound, bound_from = speaker_bound(rec, cfg["transcribe"])
        t = cfg["transcribe"]
        diar_dir = os.path.join(cfg["models"]["models_root"], cfg["models"]["diarizer_folder"])
        version = adapter(cfg, "version")
        fingerprints = {
            "master_sha256": sha256_file(master),
            "asr_model": manifest(cfg["models"]["asr_dir"]) | {"version": cfg["models"]["asr_version"]},
            "diarizer_model": manifest(diar_dir),
            "fluidaudio": version["sdk"], "adapter": version["adapter"],
            "settings_sha256": sha256_text(json.dumps(dict(t, max_speakers_effective=bound), sort_keys=True)),
        }
        if guard(rec, "transcript", out, fingerprints, force) == "unchanged":
            return out, "unchanged"

        present = {n: meta["legs"][n]["present"] for n in ("mic", "system")}
        began = time.time()
        with tempfile.TemporaryDirectory(prefix="meeting-notes.") as tmp:
            results = {}
            for name, ch in (("mic", 0), ("system", 1)):
                if not present[name]:
                    continue
                wav = os.path.join(tmp, f"{name}.wav")
                subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", master,
                                "-af", f"pan=mono|c0=c{ch}", "-ar", "16000", wav], check=True)
                results[name] = {"asr": adapter(cfg, "transcribe", "--model-dir", cfg["models"]["asr_dir"],
                                                "--version", cfg["models"]["asr_version"], wav)}
                if name == "system":
                    extra = (["--num-speakers", str(t["num_speakers"])] if t["num_speakers"] else
                             ["--max-speakers", str(bound)] if bound else [])
                    results[name]["diar"] = adapter(cfg, "diarize", "--models-root", cfg["models"]["models_root"],
                                                    *extra, wav)

        mic_words = results["mic"]["asr"]["words"] if "mic" in results else []
        sys_words = results["system"]["asr"]["words"] if "system" in results else []
        mic_words, sys_words, dedup_log = dedup(mic_words, sys_words, t["echo_min_words"])
        merges, sys_segs = [], []
        if "system" in results:
            diar, merges = merge_short_speakers(results["system"]["diar"]["segments"], t["min_speaker_s"])
            order = []
            for s in sorted(diar, key=lambda s: s["start"]):
                if s["speaker"] not in order:
                    order.append(s["speaker"])
            names = {sp: f"S{i + 1}" for i, sp in enumerate(order)}
            for m in merges:
                m["into"] = names.get(m["into"], m["into"])
            sys_segs = group(sys_words, "system", lambda w: names.get(speaker_at(diar, w), "S?"), t["pause_s"])
        mic_segs = group(mic_words, "mic", lambda w: "mic", t["pause_s"])

        segments = sorted(mic_segs + sys_segs, key=lambda s: (s["start"], s["source"]))
        for i, s in enumerate(segments):
            s["id"] = i + 1
            s["start"], s["end"] = round(s["start"], 3), round(s["end"], 3)
        speakers = {}
        for s in segments:
            sp = speakers.setdefault(s["speaker"], {"id": s["speaker"], "source": s["source"], "speech_s": 0.0})
            sp["speech_s"] = round(sp["speech_s"] + s["end"] - s["start"], 2)

        transcript = {
            "format_version": FORMAT_VERSION,
            "recording_id": meta.get("id"),
            "generated_at": now_iso(),
            "max_speakers": {"value": bound or None, "from": bound_from},
            "processing_s": round(time.time() - began, 2),
            "fingerprints": fingerprints,
            "channels": {n: {"transcribed": n in results,
                             "text_raw": results[n]["asr"]["text"] if n in results else None} for n in ("mic", "system")},
            "speakers": sorted(speakers.values(), key=lambda s: (s["source"], s["id"])),
            "filler_words": FILLER_WORDS,
            "merges": merges,
            "dedup": dedup_log,
            "assumptions": ["Speaker 'mic' is assumed to be the user; the mic also hears the room and the speakers."],
            "segments": [{k: s[k] for k in ("id", "start", "end", "source", "speaker", "text", "text_clean",
                                            "confidence", "words") } | ({"echo_of_system": True} if s.get("echo_of_system") else {})
                         for s in segments],
        }
        write_json(out, transcript)
        record_output(rec, "transcript", out, fingerprints)
        return out, "written"


