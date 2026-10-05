"""notes: transcript.json -> notes.md with a local LLM. Off until configured.

[notes] in config.toml:
  endpoint     base URL of a server on THIS machine, e.g. http://127.0.0.1:11434
  model        the model name the server knows
  api          ollama (POST /api/chat) or openai (POST /v1/chat/completions)
  chunk_chars  transcript characters per request (default 12000)

Local only, enforced: the endpoint host must be 127.0.0.1, ::1 or localhost, and
every address it resolves to must be loopback; the request goes to the resolved
loopback address. Proxies from the environment are ignored and redirects are
refused. Anything else is an error before any connection is made.

Map-reduce, no truncation: the transcript is cut into chunks of at most
chunk_chars (a single over-long segment is split by words), each chunk becomes
partial notes (prompts/notes-v1-map.md), and the partials are combined
(prompts/notes-v1-reduce.md) — in rounds, when they are themselves too long.
The model must return the four headings; otherwise the stage fails.
"""
import ipaddress, json, os, socket, urllib.error, urllib.parse, urllib.request

from .common import guard, now_iso, read_recording, record_output, recording_lock, sha256_file, sha256_text, \
    write_text

PROMPT_VERSION = "notes-v1"
PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
HEADINGS = ("## Summary", "## Decisions", "## Action items", "## Open questions")


class NotesError(RuntimeError):
    pass


def enabled(cfg):
    return bool(cfg["notes"]["endpoint"] and cfg["notes"]["model"])


def check_loopback(endpoint):
    """Returns the URL rewritten to a loopback IP; raises ValueError otherwise."""
    u = urllib.parse.urlparse(endpoint)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError(f"notes endpoint must be an http(s) URL; got {endpoint!r}")
    if u.username or u.password:
        raise ValueError("notes endpoint must not carry credentials")
    host = u.hostname
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError(f"notes endpoint host must be 127.0.0.1, ::1 or localhost; got {host!r} (local only)")
    port = u.port or (443 if u.scheme == "https" else 80)
    addrs = {ai[4][0] for ai in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)}
    if not addrs or not all(ipaddress.ip_address(a.split("%")[0]).is_loopback for a in addrs):
        raise ValueError(f"{host} resolves to {sorted(addrs)}, not only loopback; refusing")
    ip = sorted(addrs)[0]
    netloc = (f"[{ip}]" if ":" in ip else ip) + f":{port}"
    return urllib.parse.urlunparse((u.scheme, netloc, u.path.rstrip("/"), "", "", ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NotesError(f"notes endpoint answered with a redirect ({code} to {newurl}); refusing")


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def chat(cfg, base, system, user):
    n = cfg["notes"]
    if n["api"] == "ollama":
        url, body = base + "/api/chat", {"model": n["model"], "stream": False, "options": {"temperature": 0.2},
                                         "messages": [{"role": "system", "content": system},
                                                      {"role": "user", "content": user}]}
    elif n["api"] == "openai":
        url, body = base + "/v1/chat/completions", {"model": n["model"], "temperature": 0.2,
                                                    "messages": [{"role": "system", "content": system},
                                                                 {"role": "user", "content": user}]}
    else:
        raise ValueError(f"notes api must be ollama or openai; got {n['api']!r}")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with _OPENER.open(req, timeout=n["timeout_s"]) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise NotesError(f"notes endpoint returned HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise NotesError(f"notes endpoint not reachable: {e.reason}") from None
    try:
        return data["message"]["content"] if n["api"] == "ollama" else data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise NotesError("notes endpoint returned an unexpected response") from None


def mmss(t):
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def transcript_lines(transcript, budget):
    """One line per segment; a line longer than the budget is split by words."""
    lines = []
    for s in transcript["segments"]:
        prefix = f"[{mmss(s['start'])}] {s['speaker']} ({s['source']}): "
        words, cur = (s.get("text_clean") or s["text"]).split(), ""
        for w in words:
            if cur and len(prefix) + len(cur) + 1 + len(w) > budget:
                lines.append(prefix + cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(prefix + cur)
    return lines


def pack(items, budget, sep="\n"):
    """Consecutive items in groups whose joined length fits the budget (an item is never cut)."""
    groups, cur = [], []
    for it in items:
        if cur and len(sep.join(cur + [it])) > budget:
            groups.append(cur)
            cur = []
        cur.append(it)
    if cur:
        groups.append(cur)
    return groups


def context_text(rec, transcript):
    lines = [f"Speakers: " + ", ".join(f"{s['id']} ({s['source']})" for s in transcript["speakers"])]
    path = os.path.join(rec, "meeting.json")
    if os.path.exists(path):
        m = json.load(open(path))
        if m.get("state") == "matched":
            ev = m["event"]
            lines.insert(0, f"Meeting: {ev['title']} ({ev['start']} to {ev['end']})")
            if ev["invitees"]:
                lines.append("Invited (calendar; NOT speaker labels): " + ", ".join(ev["invitees"]))
    return "\n".join(lines)


def check_sections(text):
    missing = [h for h in HEADINGS if h not in text]
    if missing:
        raise NotesError(f"the model's answer lacks {', '.join(missing)}")
    return text[text.index(HEADINGS[0]):].strip()


def run(rec, cfg, force=False):
    """Returns (path, "written" | "unchanged" | "off")."""
    if not enabled(cfg):
        return None, "off"
    base = check_loopback(cfg["notes"]["endpoint"])
    with recording_lock(rec):
        meta = read_recording(rec)
        tpath = os.path.join(rec, "transcript.json")
        if not os.path.exists(tpath):
            raise NotesError("no transcript.json; run transcribe first")
        out = os.path.join(rec, "notes.md")
        map_prompt = open(os.path.join(PROMPTS, f"{PROMPT_VERSION}-map.md")).read()
        reduce_prompt = open(os.path.join(PROMPTS, f"{PROMPT_VERSION}-reduce.md")).read()
        mpath = os.path.join(rec, "meeting.json")
        n = cfg["notes"]
        fingerprints = {"transcript_sha256": sha256_file(tpath),
                        "meeting_sha256": sha256_file(mpath) if os.path.exists(mpath) else None,
                        "model": n["model"], "api": n["api"], "endpoint": n["endpoint"],
                        "chunk_chars": n["chunk_chars"], "prompt": PROMPT_VERSION,
                        "prompt_sha256": sha256_text(map_prompt + reduce_prompt)}
        if guard(rec, "notes", out, fingerprints, force) == "unchanged":
            return out, "unchanged"

        transcript = json.load(open(tpath))
        ctx = context_text(rec, transcript)
        budget = int(n["chunk_chars"])
        chunks = pack(transcript_lines(transcript, budget), budget)
        partials = []
        for i, chunk in enumerate(chunks):
            user = f"{ctx}\n\nTranscript part {i + 1} of {len(chunks)}:\n" + "\n".join(chunk)
            partials.append(check_sections(chat(cfg, base, map_prompt, user)))
        rounds = 0
        while True:  # reduce in rounds until one call holds every partial
            rounds += 1
            groups = pack(partials, budget, sep="\n\n---\n\n")
            if len(groups) == len(partials) > 1:  # each partial alone fills the budget: pair them anyway
                groups = [partials[i:i + 2] for i in range(0, len(partials), 2)]
            outs = []
            for g in groups:
                user = f"{ctx}\n\nPartial notes, in order:\n\n" + "\n\n---\n\n".join(g)
                outs.append(check_sections(chat(cfg, base, reduce_prompt, user)))
            partials = outs
            if len(groups) == 1:
                break
            if rounds > 20:
                raise NotesError("reduce did not converge; raise chunk_chars")
        title = (json.load(open(mpath)).get("event") or {}).get("title") if os.path.exists(mpath) else None
        header = "\n".join([
            f"# Notes: {title or meta.get('id')}",
            "",
            f"- Recording: {meta.get('id')}",
            f"- Transcript: sha256 {fingerprints['transcript_sha256'][:16]}",
            f"- Model: {n['model']} ({n['api']} API, {n['endpoint']})",
            f"- Prompt: {PROMPT_VERSION} (sha256 {fingerprints['prompt_sha256'][:16]})",
            f"- Generated: {now_iso()}; {len(chunks)} transcript chunk(s), {rounds} reduce round(s)",
            "- Speaker labels are from the transcript; mic is assumed to be the user.",
            "", ""])
        write_text(out, header + partials[0] + "\n")
        record_output(rec, "notes", out, fingerprints)
        return out, "written"
