"""Read VoiceInk's settings so a dropped-in recording is handled the way VoiceInk
handles a file dragged onto it (Features/AudioImport + History/AudioFileTranscriptionService).

Read-only: `defaults export com.prakashjoshipax.VoiceInk` (or a plist file in
$MEETING_NOTES_VOICEINK_PLIST, for tests). What is used:

  model         the active mode's selectedTranscriptionModelName (mode =
                activeConfigurationId in modeConfigurationsV2, else the default
                mode), else CurrentTranscriptionModel
  language      the mode's selectedLanguage
  formatting    the mode's isTextFormattingEnabled (paragraphs)
  filler words  FillerWords, else VoiceInk's default list
  enhancement   the mode's isAIEnhancementEnabled, selectedAIProvider (else the
                global selectedAIProvider), selectedPrompt -> customPrompts, and the
                Local CLI keys localCLICommandTemplate / localCLITimeoutSeconds

  dictionary    word replacements from VoiceInk's dictionary.store (SQLite, read
                only; $MEETING_NOTES_VOICEINK_DICTIONARY for tests), applied like
                its WordReplacementService (see replace_words)

Not readable from outside the app: which providers hold API keys, and VoiceInk
Refine, its local enhancement model, which only the app can call.
"""
import json, os, plistlib, re, sqlite3, subprocess, unicodedata

DOMAIN = "com.prakashjoshipax.VoiceInk"
APP_BINARY = "/Applications/VoiceInk.app/Contents/MacOS/VoiceInk"
MODELS_ROOT = os.path.expanduser("~/Library/Application Support/FluidAudio/Models")
SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/com.prakashjoshipax.VoiceInk")
WHISPER_DIR = os.path.join(SUPPORT_DIR, "WhisperModels")
NON_SPACED = ((0x3040, 0x309F), (0x30A0, 0x30FF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0x0E00, 0x0E7F))
# VoiceInk FillerWordManager.defaultFillerWords (read 2026-10-05)
DEFAULT_FILLERS = ["uh", "um", "uhm", "umm", "uhh", "uhhh", "hmm", "hm", "mmm", "mm", "mh", "ehh"]

# VoiceInk model name -> how meeting-asr runs it offline (None = not supported here).
ENGINES = {
    "parakeet-unified-0.6b": {"engine": "unified", "folder": "parakeet-unified-en-0.6b"},
    "parakeet-tdt-0.6b-v2": {"engine": "tdt", "folder": "parakeet-tdt-0.6b-v2-coreml", "version": "v2"},
    "parakeet-tdt-0.6b-v3": {"engine": "tdt", "folder": "parakeet-tdt-0.6b-v3-coreml", "version": "v3"},
    "apple-speech": {"engine": "apple"},
}
# Tried in this order when VoiceInk's model cannot run offline here.
FALLBACKS = ["parakeet-unified-0.6b", "parakeet-tdt-0.6b-v2", "parakeet-tdt-0.6b-v3", "apple-speech"]


def _decode(v):
    if isinstance(v, (bytes, bytearray)):
        v = v.decode("utf-8")
    return json.loads(v) if isinstance(v, str) else v


def read_defaults():
    path = os.environ.get("MEETING_NOTES_VOICEINK_PLIST")
    try:
        raw = open(path, "rb").read() if path else subprocess.run(
            ["/usr/bin/defaults", "export", DOMAIN, "-"], capture_output=True, check=True).stdout
        return plistlib.loads(raw)
    except (OSError, subprocess.CalledProcessError, plistlib.InvalidFileException):
        return {}


def settings():
    """VoiceInk's settings as the pipeline needs them; missing values are None."""
    d = read_defaults()
    modes = _decode(d.get("modeConfigurationsV2")) or []
    active = next((m for m in modes if m.get("id") == d.get("activeConfigurationId")), None) \
        or next((m for m in modes if m.get("isDefault")), None) or (modes[0] if modes else {})
    prompts = _decode(d.get("customPrompts")) or []
    prompt = next((p for p in prompts if p.get("id") == active.get("selectedPrompt")), None)
    return {
        "found": bool(d),
        "mode": active.get("name"),
        "model": active.get("selectedTranscriptionModelName") or d.get("CurrentTranscriptionModel"),
        "language": active.get("selectedLanguage") or d.get("SelectedLanguage"),
        "text_formatting": bool(active.get("isTextFormattingEnabled", False)),
        "filler_words": list(d["FillerWords"]) if isinstance(d.get("FillerWords"), list) else DEFAULT_FILLERS,
        "enhancement": {
            "enabled": bool(active.get("isAIEnhancementEnabled", False)),
            "provider": active.get("selectedAIProvider") or d.get("selectedAIProvider"),
            "provider_from": "mode" if active.get("selectedAIProvider") else
                             "global" if d.get("selectedAIProvider") else None,
            "model": active.get("selectedAIModel"),
            "prompt_title": prompt.get("title") if prompt else None,
            "prompt_text": prompt.get("promptText") if prompt else None,
            "use_system_instructions": bool(prompt.get("useSystemInstructions", True)) if prompt else True,
            "cli_template": d.get("localCLICommandTemplate") or "",
            "cli_timeout_s": float(d.get("localCLITimeoutSeconds") or 45),
        },
    }


def system_template(binary=None):
    """VoiceInk's enhancement system template (it wraps the prompt text in %@), read
    from the installed app at run time; None when it cannot be found unambiguously."""
    binary = binary or os.environ.get("MEETING_NOTES_VOICEINK_BINARY", APP_BINARY)
    try:
        data = open(binary, "rb").read()
    except OSError:
        return None
    found = {b for b in re.findall(rb"<SYSTEM_INSTRUCTIONS>[\s\S]{0,12000}?</SYSTEM_INSTRUCTIONS>", data)
             if b.count(b"%@") == 1 and b"<TASK_INSTRUCTIONS>" in b and b"<TRANSCRIPT>" in b}
    return found.pop().decode("utf-8") if len(found) == 1 else None


def model_files_ok(name, models_root=MODELS_ROOT):
    """(ok, reason) from the files on disk; a real load is still the final test."""
    spec = ENGINES.get(name)
    if spec is None:
        if name and name.startswith("ggml-"):
            return False, "Whisper models need a whisper.cpp binary, which is not installed"
        return False, f"{name!r} is not a model this tool can run offline"
    if spec["engine"] == "apple":
        return True, None
    folder = os.path.join(models_root, spec["folder"])
    if not os.path.isdir(folder):
        return False, f"model folder {folder} is missing"
    need = {"unified": ["parakeet_unified_encoder_int8.mlmodelc", "parakeet_unified_decoder.mlmodelc",
                        "parakeet_unified_joint_decision_single_step.mlmodelc", "vocab.json"],
            "tdt": ["Preprocessor.mlmodelc", "Decoder.mlmodelc", "parakeet_vocab.json",
                    "JointDecisionv3.mlmodelc" if spec.get("version") == "v3" else "JointDecision.mlmodelc"]}
    missing = [f for f in need[spec["engine"]] if not os.path.exists(os.path.join(folder, f))]
    return (False, f"{spec['folder']} lacks {', '.join(missing)}") if missing else (True, None)


def adapter_args(name, language, models_root=MODELS_ROOT):
    spec = ENGINES[name]
    if spec["engine"] == "apple":
        return ["--engine", "apple", "--locale", language or "en"]
    args = ["--engine", spec["engine"], "--model-dir", os.path.join(models_root, spec["folder"])]
    return args + (["--version", spec["version"]] if "version" in spec else [])


def candidates(selected, override=None):
    """Model names to try, in order, each with why it is in the list."""
    first = override or selected
    out = [(first, "config override" if override else "VoiceInk's selected model")] if first else []
    return out + [(n, "fallback") for n in FALLBACKS if n != first]


def dictionary_path():
    return os.environ.get("MEETING_NOTES_VOICEINK_DICTIONARY", os.path.join(SUPPORT_DIR, "dictionary.store"))


def word_replacements():
    """(rules, error): VoiceInk's word replacement rules, read only. Each rule is
    (original, replacement, date_added, id); VoiceInk applies all of them, enabled
    or not."""
    path = dictionary_path()
    if not os.path.exists(path):
        return [], None
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            rows = con.execute("SELECT ZORIGINALTEXT, ZREPLACEMENTTEXT, ZDATEADDED, hex(ZID) "
                               "FROM ZWORDREPLACEMENT").fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        return [], f"cannot read VoiceInk's dictionary: {e}"
    return [(o or "", r or "", d or 0, i or "") for o, r, d, i in rows], None


def _nfc(text):
    return unicodedata.normalize("NFC", text.strip())


def replace_words(text, rules):
    """VoiceInk's WordReplacementService: each rule's original is a comma list of
    variants; variants are applied longest first (then by folded text, date added,
    id), case-insensitively, as whole words (letters, marks and digits around a
    match block it) for spaced scripts and as plain substrings for CJK and Thai.
    The replacement is inserted literally."""
    variants = []
    for original, replacement, added, rid in rules:
        seen = set()
        for v in (_nfc(x) for x in original.split(",")):
            k = v.casefold()
            if v and k not in seen:
                seen.add(k)
                variants.append((v, replacement, added, rid))
    variants.sort(key=lambda r: (-len(r[0]), r[0].casefold(), r[2], r[3]))
    for v, replacement, _, _ in variants:
        spaced = not any(lo <= ord(c) <= hi for c in v for lo, hi in NON_SPACED)
        pattern = (r"(?<![^\W_])" + re.escape(v) + r"(?![^\W_])") if spaced else re.escape(v)
        text = re.sub(pattern, lambda _m: replacement, text, flags=re.IGNORECASE)
    return text
