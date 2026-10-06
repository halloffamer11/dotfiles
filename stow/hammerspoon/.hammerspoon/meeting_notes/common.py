"""Shared pieces: settings, hashing, atomic writes, the per-recording lock, and the
stage guard (skip when unchanged, never overwrite a hand-edited output)."""
import contextlib, fcntl, hashlib, json, os, re, subprocess, tempfile, time

FORMAT_VERSION = 1
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = os.path.join(os.path.dirname(FFMPEG), "ffprobe")
NO_NETWORK = "(version 1)(allow default)(deny network*)"
MODELS_ROOT = "~/Library/Application Support/FluidAudio/Models"
DEFAULTS = {
    "paths": {"recordings": "~/Recordings", "adapter": "~/.local/bin/meeting-asr"},
    "models": {"models_root": MODELS_ROOT, "diarizer_folder": "speaker-diarization"},
    "transcribe": {"model": "", "diarize": False, "pause_s": 1.0, "min_speaker_s": 3.0, "echo_min_words": 3,
                   "max_speakers": 0, "num_speakers": 0, "no_network": True, "keep_master": False},
    "enhance": {"enabled": False, "timeout_s": 0},
    "run": {"auto_run": False},
}
PATH_KEYS = {("paths", "recordings"), ("paths", "adapter"), ("models", "models_root")}


class Refused(Exception):
    """An output was edited by hand; it is kept as it is (exit 4)."""


class Busy(Exception):
    """Another run holds this recording's lock (exit 75)."""


# ---------- settings ----------

def parse_toml_subset(text):
    """[section] headers and key = "string" | ["string", ...] | number | true/false lines; # comments."""
    out = {}
    section = out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"\[([A-Za-z0-9_.-]+)\]\s*(#.*)?", line)
        if m:
            section = out.setdefault(m.group(1), {})
            continue
        m = re.fullmatch(r'([A-Za-z0-9_-]+)\s*=\s*\[((?:\s*"[^"]*"\s*,?)*)\]\s*(#.*)?', line)
        if m:
            section[m.group(1)] = re.findall(r'"([^"]*)"', m.group(2))
            continue
        m = re.fullmatch(r'([A-Za-z0-9_-]+)\s*=\s*(?:"([^"]*)"|([^#\s]+))\s*(#.*)?', line)
        if not m:
            raise ValueError(f"cannot read config line: {raw!r}")
        key, string, bare = m.group(1), m.group(2), m.group(3)
        if string is not None:
            val = string
        elif bare in ("true", "false"):
            val = bare == "true"
        else:
            val = float(bare) if "." in bare else int(bare)
        section[key] = val
    return out


def settings():
    path = os.path.expanduser(os.environ.get("MEETING_NOTES_CONFIG", "~/.config/meeting-notes/config.toml"))
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    if os.path.exists(path):
        for sec, vals in parse_toml_subset(open(path).read()).items():
            cfg.setdefault(sec, {}).update(vals)
    for sec, key in PATH_KEYS:
        if cfg[sec].get(key):
            cfg[sec][key] = os.path.expanduser(cfg[sec][key])
    cfg["config_path"] = path
    return cfg


# ---------- files ----------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def manifest(folder):
    """Hash of every file's relative path and size, plus the small JSON files' bytes:
    detects a changed or swapped model without reading hundreds of MB each run."""
    h = hashlib.sha256()
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for name in sorted(files):
            p = os.path.join(root, name)
            rel = os.path.relpath(p, folder)
            h.update(f"{rel}\0{os.path.getsize(p)}\0".encode())
            if name.endswith(".json") or name == ".fluidaudio-revision":
                h.update(open(p, "rb").read())
    rev = os.path.join(folder, ".fluidaudio-revision")
    return {"folder": os.path.basename(folder.rstrip("/")), "manifest_sha256": h.hexdigest(),
            "revision": open(rev).read().strip() if os.path.exists(rev) else None}


def write_text(path, text):
    """Atomic (temp file + rename), mode 600."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def write_json(path, obj):
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def adapter(cfg, *args, stdin=None):
    """Run meeting-asr; with no_network (the default) inside a no-network sandbox."""
    cmd = [cfg["paths"]["adapter"], *args]
    if cfg["transcribe"]["no_network"]:
        cmd = ["/usr/bin/sandbox-exec", "-p", NO_NETWORK, *cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, input=stdin)
    if r.returncode != 0:
        raise RuntimeError(f"meeting-asr {args[0]} failed: {r.stderr.strip()[-500:]}")
    return json.loads(r.stdout)


# ---------- lock and stage guard ----------

_held = {}


@contextlib.contextmanager
def recording_lock(rec):
    """One lock per recording, re-entrant within this process (run holds it across stages)."""
    if rec in _held:
        _held[rec][1] += 1
        try:
            yield
        finally:
            _held[rec][1] -= 1
        return
    f = open(os.path.join(rec, ".meeting-notes.lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        raise Busy("another run holds this recording's lock")
    _held[rec] = [f, 1]
    try:
        yield
    finally:
        del _held[rec]
        f.close()


def lock_is_free(rec):
    if rec in _held:
        return False
    path = os.path.join(rec, ".meeting-notes.lock")
    if not os.path.exists(path):
        return True
    with open(path) as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False


def _state_path(rec):
    return os.path.join(rec, ".meeting-notes-state.json")


def load_state(rec):
    p = _state_path(rec)
    return json.load(open(p)) if os.path.exists(p) else {}


def guard(rec, stage, out, fingerprints, force):
    """'edited' (raise Refused), 'unchanged' (skip) or 'go'. Hand edits win over --force."""
    entry = load_state(rec).get(stage, {})
    if os.path.exists(out) and entry.get("output_sha256") != sha256_file(out):
        raise Refused(f"{os.path.basename(out)} was edited by hand; not overwriting it (move it away to regenerate)")
    if not force and os.path.exists(out) and entry.get("fingerprints") == fingerprints:
        return "unchanged"
    return "go"


def record_output(rec, stage, out, fingerprints):
    state = load_state(rec)
    state[stage] = {"fingerprints": fingerprints, "output_sha256": sha256_file(out), "at": now_iso()}
    write_json(_state_path(rec), state)


def names(rec):
    """The files a user keeps are named after the recording (its folder name, such
    as meeting-2026-10-06-081106), so each still says which meeting it is when
    copied into a flat folder: <id>.m4a (stereo audio), <id>.md (transcript),
    <id>.json (transcript details) and <id>.enhanced.md."""
    base = os.path.basename(os.path.normpath(rec))
    return {"audio": os.path.join(rec, f"{base}.m4a"), "transcript": os.path.join(rec, f"{base}.md"),
            "details": os.path.join(rec, f"{base}.json"), "enhanced": os.path.join(rec, f"{base}.enhanced.md")}


LEGACY_NAMES = {"audio": "listen.m4a", "transcript": "transcript.md", "details": "transcript.json",
                "enhanced": "enhanced.md"}


def migrate_names(rec):
    """Rename a recording's files from the old generic names (listen.m4a,
    transcript.md, transcript.json, enhanced.md) to the named ones."""
    new = names(rec)
    for key, old in LEGACY_NAMES.items():
        path = os.path.join(rec, old)
        if os.path.exists(path) and not os.path.exists(new[key]):
            os.replace(path, new[key])
            if key == "audio":
                meta_path = os.path.join(rec, "recording.json")
                meta = json.load(open(meta_path))
                meta.setdefault("files", {})["listen"] = os.path.basename(new[key])
                write_json(meta_path, meta)


def audio_source(rec):
    """master.caf while it exists; after transcription it is removed and the stereo
    <id>.m4a (ch0 = mic, ch1 = system) is the recording."""
    master = os.path.join(rec, "master.caf")
    return master if os.path.exists(master) else names(rec)["audio"]


def probe(path):
    """(channels, sample rate, duration s) or None."""
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=channels,sample_rate:format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        s = j["streams"][0]
        return int(s["channels"]), int(s["sample_rate"]), float(j["format"]["duration"])
    except (ValueError, KeyError, IndexError):
        return None


def read_recording(rec):
    """recording.json, after migrate_names (callers hold the recording lock)."""
    path = os.path.join(rec, "recording.json")
    if os.path.exists(path):
        migrate_names(rec)
    if not (os.path.exists(path) and os.path.exists(audio_source(rec))):
        raise ValueError(f"{rec} has no recording.json + master.caf or .m4a "
                         "(older flat recordings are not supported)")
    meta = json.load(open(path))
    if meta.get("format_version") != 1 or meta.get("state") not in ("recorded", "partial"):
        raise ValueError(f"recording state is {meta.get('state')!r}; nothing to process")
    return meta


def set_pipeline(rec, state, reason=None, enhancement=None):
    """Pipeline progress lives under recording.json "pipeline"; the capture state is untouched."""
    path = os.path.join(rec, "recording.json")
    meta = json.load(open(path))
    meta["pipeline"] = {"state": state, "reason": reason, "enhancement": enhancement, "updated": now_iso()}
    write_json(path, meta)
