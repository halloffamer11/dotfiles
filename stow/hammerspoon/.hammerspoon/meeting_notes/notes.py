"""notes: hand transcript.json to the agent CLI on this machine -> notes.md.

No model of our own: the notes come from whatever agent CLI the machine already
has. Off until [notes] command is set in config.toml (there is no default):

  command      argv template, e.g. ["claude", "-p"] or
               ["codex", "exec", "--skip-git-repo-check", "-o", "{output}"]
               "{output}": the CLI writes its answer to that file; without it,
               the answer is the CLI's stdout. A bare program name is looked up
               on PATH plus ~/.local/bin, /opt/homebrew/bin and /usr/local/bin
               (Hammerspoon starts tasks with a minimal PATH).
  prompt_file  optional; default prompts/notes-v1.md (versioned in the repo)
  timeout_s    default 900; the whole process group is killed after it

Hand-off: stdin = the prompt, then the transcript as plain text between
<transcript> tags, one line per segment: [time] SPEAKER (source): text. The CLI
runs in the recording folder with the user's normal network access; it is the
user's own tool. (The no-network rule covers transcription only.)

The answer should have the four headings (Summary, Decisions, Action items,
Open questions). It is saved either way; without them the stage reports
"unstructured" and the pipeline state is notes-unstructured.
"""
import json, os, shutil, signal, subprocess, tempfile

from .common import guard, now_iso, read_recording, record_output, recording_lock, sha256_file, sha256_text, \
    write_text

PROMPT_VERSION = "notes-v1"
DEFAULT_PROMPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", f"{PROMPT_VERSION}.md")
HEADINGS = ("## Summary", "## Decisions", "## Action items", "## Open questions")
EXTRA_PATH = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin")


class NotesError(RuntimeError):
    pass


def enabled(cfg):
    return bool(cfg["notes"]["command"])


def resolve(program):
    if os.path.isabs(program):
        return program if os.access(program, os.X_OK) else None
    path = os.pathsep.join([os.environ.get("PATH", "")] + [os.path.expanduser(p) for p in EXTRA_PATH])
    return shutil.which(program, path=path)


def mmss(t):
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def render(transcript):
    return "\n".join(f"[{mmss(s['start'])}] {s['speaker']} ({s['source']}): {s.get('text_clean') or s['text']}"
                     for s in transcript["segments"])


def context(rec, transcript):
    lines = ["Speakers: " + ", ".join(f"{s['id']} ({s['source']})" for s in transcript["speakers"])]
    path = os.path.join(rec, "meeting.json")
    if os.path.exists(path):
        m = json.load(open(path))
        if m.get("state") == "matched":
            ev = m["event"]
            lines.insert(0, f"Meeting: {ev['title']} ({ev['start']} to {ev['end']})")
            if ev["invitees"]:
                lines.append("Invited (calendar; NOT speaker labels): " + ", ".join(ev["invitees"]))
    return "\n".join(lines)


def structured(text):
    return all(h in text for h in HEADINGS)


def call(argv, stdin, cwd, timeout):
    """Run the CLI in its own process group; kill the whole group on timeout."""
    p = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
    try:
        out, err = p.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        raise NotesError(f"notes command timed out after {timeout} s") from None
    if p.returncode != 0:
        raise NotesError(f"notes command exited {p.returncode}: {err.strip()[-300:]}")
    return out


def run(rec, cfg, force=False):
    """Returns (path, "written" | "unstructured" | "unchanged" | "off")."""
    n = cfg["notes"]
    if not enabled(cfg):
        return None, "off"
    template = n["command"] if isinstance(n["command"], list) else [n["command"]]
    program = resolve(template[0])
    if not program:
        raise NotesError(f"notes command {template[0]!r} not found")
    prompt_path = os.path.expanduser(n["prompt_file"]) if n["prompt_file"] else DEFAULT_PROMPT
    prompt = open(prompt_path).read()
    with recording_lock(rec):
        meta = read_recording(rec)
        tpath = os.path.join(rec, "transcript.json")
        if not os.path.exists(tpath):
            raise NotesError("no transcript.json; run transcribe first")
        out = os.path.join(rec, "notes.md")
        mpath = os.path.join(rec, "meeting.json")
        fingerprints = {"transcript_sha256": sha256_file(tpath),
                        "meeting_sha256": sha256_file(mpath) if os.path.exists(mpath) else None,
                        "command": template, "prompt_sha256": sha256_text(prompt)}
        if guard(rec, "notes", out, fingerprints, force) == "unchanged":
            return out, "unchanged" if structured(open(out).read()) else "unstructured"

        transcript = json.load(open(tpath))
        stdin = f"{prompt}\n\n{context(rec, transcript)}\n\n<transcript>\n{render(transcript)}\n</transcript>\n"
        with tempfile.TemporaryDirectory(dir=rec, prefix=".notes-") as tmp:
            answer_file = os.path.join(tmp, "answer.md")
            argv = [program] + [a.replace("{output}", answer_file) for a in template[1:]]
            stdout = call(argv, stdin, rec, n["timeout_s"])
            uses_file = any("{output}" in a for a in template)
            answer = (open(answer_file).read() if os.path.exists(answer_file) else "") if uses_file else stdout
        answer = answer.strip()
        if not answer:
            raise NotesError("notes command returned nothing")
        ok = structured(answer)
        title = (json.load(open(mpath)).get("event") or {}).get("title") if os.path.exists(mpath) else None
        header = "\n".join([
            f"# Notes: {title or meta.get('id')}",
            "",
            f"- Recording: {meta.get('id')}",
            f"- Transcript: sha256 {fingerprints['transcript_sha256'][:16]}",
            f"- Written by: {' '.join(template)}",
            f"- Prompt: {PROMPT_VERSION if not n['prompt_file'] else prompt_path} "
            f"(sha256 {fingerprints['prompt_sha256'][:16]})",
            f"- Generated: {now_iso()}" + ("" if ok else "; the answer lacks the expected headings"),
            "- Speaker labels are from the transcript; mic is assumed to be the user.",
            "", ""])
        body = answer[answer.index(HEADINGS[0]):] if ok else answer
        write_text(out, header + body + "\n")
        record_output(rec, "notes", out, fingerprints)
        return out, "written" if ok else "unstructured"
