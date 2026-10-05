"""match: which calendar event was this recording? -> meeting.json (format_version 1).

Sources ([match] source in config.toml):
  none      (default) no calendar; meeting.json says unmatched
  ics_file  path = a local .ics file (for example an export or a synced copy)
  ics_url   path = a file:// URL; any other scheme is refused (no network)

Rule: the recording window is recording.json's actual start/end (requested if
there is no actual). An event is a candidate when it overlaps the window by at
least min_overlap of the shorter of the two. The longest overlap wins; when the
runner-up overlaps by 80 % or more of the winner's overlap, the match is
ambiguous and meeting.json stays unmatched with the candidates listed. All-day
and cancelled events never match.

Recurrence: RRULE FREQ=DAILY or WEEKLY with INTERVAL, COUNT, UNTIL and BYDAY;
EXDATE; RECURRENCE-ID overrides. Other rules match only the first occurrence
(noted in meeting.json as unsupported_rrule).

Invitees (ATTENDEE lines) are context for the notes and a speaker-count bound
for transcribe; they are never speaker names.
"""
import datetime as dt, json, os, re, urllib.parse
from zoneinfo import ZoneInfo

from .common import FORMAT_VERSION, guard, now_iso, read_recording, record_output, recording_lock, sha256_file, \
    sha256_text, write_json

UTC = dt.timezone.utc
DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text).splitlines()


def prop(line):
    """'NAME;K=V;K2=V2:value' -> (NAME, {K: V}, value)."""
    m = re.match(r"([^:;]+)((?:;[^:;]+=(?:\"[^\"]*\"|[^:;]*))*):(.*)", line)
    if not m:
        return None, {}, ""
    params = {k.upper(): v.strip('"') for k, v in re.findall(r";([^=;]+)=(\"[^\"]*\"|[^:;]*)", m.group(2))}
    return m.group(1).upper(), params, m.group(3)


def parse_dt(value, params):
    """Returns an aware datetime, or None for an all-day DATE."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return None
    t = dt.datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return t.replace(tzinfo=UTC)
    if "TZID" in params:
        return t.replace(tzinfo=ZoneInfo(params["TZID"]))
    return t.astimezone()  # floating time: this machine's zone


def parse_duration(value):
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not m:
        return None
    sign = -1 if m.group(1) == "-" else 1
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    return sign * dt.timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


def read_events(text):
    events, cur = [], None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {"attendees": [], "exdates": []}
        elif line == "END:VEVENT" and cur is not None:
            events.append(cur)
            cur = None
        elif cur is not None:
            name, params, value = prop(line)
            if name in ("DTSTART", "DTEND", "RECURRENCE-ID"):
                cur[name] = parse_dt(value, params)
                cur[name + "_allday"] = cur[name] is None
            elif name == "DURATION":
                cur["DURATION"] = parse_duration(value)
            elif name == "EXDATE":
                cur["exdates"] += [parse_dt(v, params) for v in value.split(",")]
            elif name == "ATTENDEE":
                cur["attendees"].append(params.get("CN") or re.sub(r"(?i)^mailto:", "", value))
            elif name in ("UID", "SUMMARY", "STATUS", "RRULE"):
                cur[name] = value.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ")
    return events


def occurrences(ev, lo, hi):
    """(start, end) pairs of one event that can touch [lo, hi]; flag unsupported rules."""
    start = ev.get("DTSTART")
    if start is None:
        return [], False
    length = (ev["DTEND"] - start) if ev.get("DTEND") else (ev.get("DURATION") or dt.timedelta(0))
    rule = dict(p.split("=", 1) for p in ev["RRULE"].split(";") if "=" in p) if ev.get("RRULE") else None
    if not rule:
        return [(start, start + length)], False
    freq = rule.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        return [(start, start + length)], True
    interval = int(rule.get("INTERVAL", 1))
    count = int(rule["COUNT"]) if "COUNT" in rule else None
    until = parse_dt(rule["UNTIL"], {}) if "UNTIL" in rule else None
    if until and until.tzinfo is None:
        until = until.replace(tzinfo=start.tzinfo)
    days = sorted(DAYS[d[-2:]] for d in rule["BYDAY"].split(",")) if freq == "WEEKLY" and "BYDAY" in rule \
        else [start.weekday()]
    exdates = {e for e in ev["exdates"] if e}
    out, n = [], 0
    week0 = start.date() - dt.timedelta(days=start.weekday())
    for step in range(0, 20000):
        if freq == "DAILY":
            cands = [start + dt.timedelta(days=step * interval)]
        else:
            monday = week0 + dt.timedelta(weeks=step * interval)
            cands = [dt.datetime.combine(monday + dt.timedelta(days=d), start.timetz()) for d in days]
            cands = [c for c in cands if c >= start]
        for c in cands:
            if (until and c > until) or (count is not None and n >= count) or c - length > hi:
                return out, False
            n += 1
            if c not in exdates and c + length >= lo:
                out.append((c, c + length))
    return out, False


def run(rec, cfg, force=False):
    """Returns (path, "written" | "unchanged")."""
    with recording_lock(rec):
        meta = read_recording(rec)
        m = cfg["match"]
        out = os.path.join(rec, "meeting.json")
        src, text = m["source"], None
        if src == "ics_url":
            u = urllib.parse.urlparse(m["path"])
            if u.scheme != "file":
                raise ValueError(f"ics_url must be a file:// URL (no network); got {m['path']!r}")
            path = urllib.parse.unquote(u.path)
        elif src == "ics_file":
            path = m["path"]
        elif src == "none":
            path = None
        else:
            raise ValueError(f"unknown match source {src!r} (none, ics_file, ics_url)")
        fingerprints = {"recording": sha256_text(json.dumps([meta.get("actual"), meta.get("requested")], sort_keys=True)),
                        "calendar_sha256": sha256_file(path) if path else None,
                        "settings_sha256": sha256_text(json.dumps(m, sort_keys=True))}
        if guard(rec, "meeting", out, fingerprints, force) == "unchanged":
            return out, "unchanged"

        window = meta.get("actual") if (meta.get("actual") or {}).get("start") else meta.get("requested")
        lo = dt.datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
        hi = dt.datetime.fromisoformat(window["end"].replace("Z", "+00:00"))
        result = {"format_version": FORMAT_VERSION, "recording_id": meta.get("id"), "generated_at": now_iso(),
                  "source": src, "window": {"start": window["start"], "end": window["end"]},
                  "state": "unmatched", "reason": None, "event": None, "candidates": []}
        if path is None:
            result["reason"] = "no calendar source configured"
        else:
            events = read_events(open(path, encoding="utf-8", errors="replace").read())
            overrides = {(e.get("UID"), e["RECURRENCE-ID"]): e for e in events if e.get("RECURRENCE-ID")}
            rec_len = (hi - lo).total_seconds()
            cands, unsupported = [], False
            for e in events:
                if e.get("RECURRENCE-ID") or e.get("DTSTART_allday") or e.get("STATUS") == "CANCELLED":
                    continue
                occ, bad = occurrences(e, lo, hi)
                unsupported |= bad
                for s, f in occ:
                    o = overrides.get((e.get("UID"), s), e)
                    if o is not e:
                        if o.get("STATUS") == "CANCELLED" or o.get("DTSTART") is None:
                            continue
                        s = o["DTSTART"]
                        f = o["DTEND"] if o.get("DTEND") else s + (o.get("DURATION") or (f - s))
                    overlap = (min(f, hi) - max(s, lo)).total_seconds()
                    shorter = min(rec_len, (f - s).total_seconds()) or 1
                    if overlap > 0 and overlap >= m["min_overlap"] * shorter:
                        cands.append({"uid": o.get("UID"), "title": o.get("SUMMARY", ""), "start": s.isoformat(),
                                      "end": f.isoformat(), "overlap_s": round(overlap),
                                      "invitees": o.get("attendees", [])})
            for e in events:  # overrides moved into the window from elsewhere
                if e.get("RECURRENCE-ID") and e.get("DTSTART") and e.get("STATUS") != "CANCELLED":
                    s, f = e["DTSTART"], e.get("DTEND") or e["DTSTART"] + (e.get("DURATION") or dt.timedelta(0))
                    overlap = (min(f, hi) - max(s, lo)).total_seconds()
                    shorter = min(rec_len, (f - s).total_seconds()) or 1
                    if overlap > 0 and overlap >= m["min_overlap"] * shorter \
                            and not any(c["uid"] == e.get("UID") and c["start"] == s.isoformat() for c in cands):
                        cands.append({"uid": e.get("UID"), "title": e.get("SUMMARY", ""), "start": s.isoformat(),
                                      "end": f.isoformat(), "overlap_s": round(overlap), "invitees": e["attendees"]})
            cands.sort(key=lambda c: -c["overlap_s"])
            result["candidates"] = [{k: c[k] for k in ("title", "start", "end", "overlap_s")} for c in cands]
            if unsupported:
                result["unsupported_rrule"] = True
            if not cands:
                result["reason"] = "no event overlaps the recording enough"
            elif len(cands) > 1 and cands[1]["overlap_s"] >= 0.8 * cands[0]["overlap_s"]:
                result["reason"] = f"ambiguous: {len(cands)} events overlap about equally"
            else:
                c = cands[0]
                result["state"], result["reason"] = "matched", None
                result["event"] = {"uid": c["uid"], "title": c["title"], "start": c["start"], "end": c["end"],
                                   "invitees": c["invitees"], "invitee_count": len(c["invitees"])}
        write_json(out, result)
        record_output(rec, "meeting", out, fingerprints)
        return out, "written"
