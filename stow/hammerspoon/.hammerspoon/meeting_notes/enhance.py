"""enhance: transcript.txt -> enhanced.md, the way VoiceInk enhances a transcript
with its "Local CLI" AI provider. Optional, on top of transcription.

Runs only when all of these hold; otherwise it is skipped and the reason is kept
in recording.json "pipeline":
  - [enhance] enabled = true in config.toml (off by default: the CLI is the
    user's own tool and runs with normal network access)
  - VoiceInk's active mode has AI enhancement on
  - its provider is Local CLI (the mode's selectedAIProvider, else the global
    one) and localCLICommandTemplate is set. Any other provider (a cloud one,
    or VoiceInk Refine, which only the app itself can call) is skipped.
  - VoiceInk's system template can be read from the installed app, when the
    selected prompt uses system instructions (nothing of it is copied here)

The call is VoiceInk's LocalCLIService contract: `/bin/zsh -lc <template>` with
VOICEINK_SYSTEM_PROMPT, VOICEINK_USER_PROMPT and VOICEINK_FULL_PROMPT in the
environment; the full prompt also goes to stdin unless the template passes
$VOICEINK_FULL_PROMPT as an argument; the answer is stdout. System prompt = the
mode's prompt text inside VoiceInk's template; user prompt = the transcript in
<TRANSCRIPT> tags. Timeout: [enhance] timeout_s, else VoiceInk's
localCLITimeoutSeconds. It runs in an empty temporary folder. Not mirrored:
VoiceInk's custom vocabulary block (in its own database).
"""
import os, signal, subprocess, tempfile

from . import voiceink
from .common import guard, now_iso, read_recording, record_output, recording_lock, sha256_file, sha256_text, \
    write_text

EXTRA_PATH = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin")


class Skipped(Exception):
    """Enhancement does not apply; the message says why."""


def full_prompt(system, user):
    return (f"# System Message\n<SYSTEM_MESSAGE>\n{system}\n</SYSTEM_MESSAGE>\n\n"
            f"# User Message Payload\n<USER_MESSAGE_PAYLOAD>\n{user}\n</USER_MESSAGE_PAYLOAD>")


def plan(cfg):
    """The VoiceInk settings to use, or raise Skipped."""
    if not cfg["enhance"]["enabled"]:
        raise Skipped("off ([enhance] enabled = false)")
    vi = voiceink.settings()
    e = vi["enhancement"]
    if not vi["found"]:
        raise Skipped("VoiceInk settings not found")
    if not e["enabled"]:
        raise Skipped(f"VoiceInk mode {vi['mode']!r} has AI enhancement off")
    if e["provider"] != "Local CLI":
        who = e["provider"] or "its first connected provider (none chosen)"
        raise Skipped(f"VoiceInk enhancement uses {who}, model {e['model']!r}, not Local CLI")
    if not e["cli_template"].strip():
        raise Skipped("VoiceInk Local CLI command template is empty")
    if not e["prompt_text"]:
        raise Skipped("VoiceInk mode has no prompt selected")
    system = e["prompt_text"]
    if e["use_system_instructions"]:
        template = voiceink.system_template()
        if template is None:
            raise Skipped("cannot read VoiceInk's system template from the installed app")
        system = template.replace("%@", e["prompt_text"], 1)
    return e, system


def call(template, system, user, timeout):
    env = dict(os.environ, VOICEINK_SYSTEM_PROMPT=system, VOICEINK_USER_PROMPT=user,
               VOICEINK_FULL_PROMPT=full_prompt(system, user))
    env["PATH"] = os.pathsep.join([os.path.expanduser(p) for p in EXTRA_PATH] + [env.get("PATH", "")])
    stdin = None if "$VOICEINK_FULL_PROMPT" in template or "${VOICEINK_FULL_PROMPT}" in template \
        else env["VOICEINK_FULL_PROMPT"]
    with tempfile.TemporaryDirectory(prefix="meeting-notes-enhance.") as cwd:
        p = subprocess.Popen(["/bin/zsh", "-lc", template], cwd=cwd, env=env, text=True, start_new_session=True,
                             stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = p.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.communicate()
            raise RuntimeError(f"enhancement command timed out after {timeout:g} s") from None
    if p.returncode != 0:
        raise RuntimeError(f"enhancement command exited {p.returncode}: {err.strip()[-300:]}")
    if not out.strip():
        raise RuntimeError("enhancement command returned nothing")
    return out.strip()


def run(rec, cfg, force=False):
    """Returns (path, "written" | "unchanged") or (None, "skipped: <reason>")."""
    try:
        e, system = plan(cfg)
    except Skipped as s:
        return None, f"skipped: {s}"
    with recording_lock(rec):
        meta = read_recording(rec)
        src = os.path.join(rec, "transcript.txt")
        if not os.path.exists(src):
            raise RuntimeError("no transcript.txt; run transcribe first")
        out = os.path.join(rec, "enhanced.md")
        timeout = float(cfg["enhance"]["timeout_s"] or e["cli_timeout_s"])
        fingerprints = {"transcript_sha256": sha256_file(src), "template": e["cli_template"],
                        "system_sha256": sha256_text(system), "timeout_s": timeout}
        if guard(rec, "enhanced", out, fingerprints, force) == "unchanged":
            return out, "unchanged"
        text = open(src).read().strip()
        answer = call(e["cli_template"], system, f"\n<TRANSCRIPT>\n{text}\n</TRANSCRIPT>", timeout)
        header = "\n".join([
            f"<!-- enhanced by VoiceInk's Local CLI setting: {e['cli_template']}",
            f"     prompt: {e['prompt_title']}; transcript sha256 {fingerprints['transcript_sha256'][:16]};"
            f" recording {meta.get('id')}; {now_iso()} -->", "", ""])
        write_text(out, header + answer + "\n")
        record_output(rec, "enhanced", out, fingerprints)
        return out, "written"
