use chrono::{DateTime, Duration, FixedOffset, TimeZone};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::Path;

use crate::event::{DispatchFinishEvent, DispatchStartEvent, Event, Lane, UsageDoc};

/// Lifecycle state for an active dispatch thread.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ThreadState {
    Run,
    Stale,
}

impl ThreadState {
    pub fn as_str(&self) -> &'static str {
        match self {
            ThreadState::Run => "run",
            ThreadState::Stale => "stale",
        }
    }
}

impl std::fmt::Display for ThreadState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl PartialEq<str> for ThreadState {
    fn eq(&self, other: &str) -> bool {
        self.as_str() == other
    }
}

impl PartialEq<&str> for ThreadState {
    fn eq(&self, other: &&str) -> bool {
        self.as_str() == *other
    }
}

/// An open dispatch thread from a `dispatch.start` without a corresponding `dispatch.finish`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OpenThread {
    pub thread_id: String,
    pub lane: String,
    #[serde(default)]
    pub class: Option<String>,
    #[serde(default)]
    pub effort: Option<String>,
    pub timeout_s: u64,
    #[serde(default)]
    pub cwd: Option<String>,
    #[serde(default)]
    pub brief: Option<String>,
    #[serde(default)]
    pub out: Option<String>,
    #[serde(default)]
    pub write: Option<String>,
    pub start_ts: DateTime<chrono::FixedOffset>,
    pub state: ThreadState,
    pub elapsed_s: u64,
}

pub type Thread = OpenThread;

/// Single observation in a lane's remaining weekly quota time series.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SeriesPoint {
    pub ts: DateTime<chrono::FixedOffset>,
    pub remaining_weekly: Option<f64>,
}

impl SeriesPoint {
    pub fn new(ts: DateTime<chrono::FixedOffset>, remaining_weekly: Option<f64>) -> Self {
        Self {
            ts,
            remaining_weekly: remaining_weekly.map(clamp_fraction),
        }
    }

    pub fn value(&self) -> Option<f64> {
        self.remaining_weekly
    }
}

impl PartialEq<(DateTime<chrono::FixedOffset>, Option<f64>)> for SeriesPoint {
    fn eq(&self, other: &(DateTime<chrono::FixedOffset>, Option<f64>)) -> bool {
        self.ts == other.0 && self.remaining_weekly == other.1
    }
}

/// Selectable burn window for time series aggregation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Window {
    #[serde(rename = "1h")]
    Hour1,
    #[serde(rename = "24h")]
    Hour24,
    #[serde(rename = "7d")]
    Day7,
}

impl Window {
    pub fn duration(&self) -> Duration {
        match self {
            Window::Hour1 => Duration::hours(1),
            Window::Hour24 => Duration::hours(24),
            Window::Day7 => Duration::days(7),
        }
    }
}

pub trait IntoDuration {
    fn into_duration(self) -> Duration;
}

impl IntoDuration for Duration {
    fn into_duration(self) -> Duration {
        self
    }
}

impl IntoDuration for Window {
    fn into_duration(self) -> Duration {
        self.duration()
    }
}

impl IntoDuration for std::time::Duration {
    fn into_duration(self) -> Duration {
        Duration::from_std(self).unwrap_or(Duration::zero())
    }
}

/// Point-in-time view of meters, open threads, time series, and cache freshness.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Snapshot {
    pub meters: Vec<Lane>,
    pub threads: Vec<OpenThread>,
    pub series: BTreeMap<String, Vec<SeriesPoint>>,
    pub cache_age_s: Option<f64>,
}

impl Snapshot {
    pub fn cache_age_secs(&self) -> Option<u64> {
        self.cache_age_s.map(|s| s.max(0.0) as u64)
    }
}

/// Clamp any fraction to 0.0..=1.0. TUI widgets panic if ratios are outside this range.
pub fn clamp_fraction(v: f64) -> f64 {
    if v.is_nan() || v <= 0.0 {
        0.0
    } else if v > 1.0 {
        1.0
    } else {
        v
    }
}

/// Clamps all fractional quota fields (`remaining_5h`, `remaining_weekly`, `r`) of a lane.
pub fn clamp_lane(mut lane: Lane) -> Lane {
    lane.remaining_5h = lane.remaining_5h.map(clamp_fraction);
    lane.remaining_weekly = lane.remaining_weekly.map(clamp_fraction);
    lane.r = lane.r.map(clamp_fraction);
    lane
}

/// Pure fold function aggregating events and optional cached probe document into a Snapshot.
pub fn fold<Tz: TimeZone, W: IntoDuration>(
    events: &[Event],
    usage_doc: Option<&UsageDoc>,
    now: DateTime<Tz>,
    window: W,
) -> Snapshot {
    let now_utc = now.with_timezone(&chrono::Utc);
    let window_dur = window.into_duration();
    let start_window = now_utc - window_dur;

    let meters = if let Some(doc) = usage_doc {
        doc.lanes.iter().cloned().map(clamp_lane).collect()
    } else {
        events
            .iter()
            .filter_map(|e| match e {
                Event::Meter(m) => Some(m),
                _ => None,
            })
            .max_by_key(|m| m.ts)
            .map(|m| m.lanes.iter().cloned().map(clamp_lane).collect())
            .unwrap_or_default()
    };

    let now_epoch_s =
        now_utc.timestamp() as f64 + (now_utc.timestamp_subsec_nanos() as f64 / 1_000_000_000.0);
    let cache_age_s = usage_doc.map(|d| (now_epoch_s - d.probed_at).max(0.0));

    let finished_threads: HashSet<&str> = events
        .iter()
        .filter_map(|e| match e {
            Event::DispatchFinish(f) => Some(f.thread_id.as_str()),
            _ => None,
        })
        .collect();

    let mut threads = Vec::new();
    let mut seen_starts = HashSet::new();
    for e in events {
        if let Event::DispatchStart(s) = e {
            if !finished_threads.contains(s.thread_id.as_str())
                && seen_starts.insert(s.thread_id.as_str())
            {
                let start_ts_utc = s.ts.with_timezone(&chrono::Utc);
                let timeout_duration = Duration::seconds(s.timeout_s as i64);
                let timeout_deadline = start_ts_utc + timeout_duration;
                let state = if now_utc > timeout_deadline {
                    ThreadState::Stale
                } else {
                    ThreadState::Run
                };
                let elapsed_duration = now_utc.signed_duration_since(start_ts_utc);
                let elapsed_s = if elapsed_duration.num_seconds() > 0 {
                    elapsed_duration.num_seconds() as u64
                } else {
                    0
                };

                threads.push(OpenThread {
                    thread_id: s.thread_id.clone(),
                    lane: s.lane.clone(),
                    class: s.class.clone(),
                    effort: s.effort.clone(),
                    timeout_s: s.timeout_s,
                    cwd: s.cwd.clone(),
                    brief: s.brief.clone(),
                    out: s.out.clone(),
                    write: s.write.clone(),
                    start_ts: s.ts,
                    state,
                    elapsed_s,
                });
            }
        }
    }

    // Missing weekly is preserved as a gap (None) rather than falling back to hook r.
    let mut series: BTreeMap<String, Vec<SeriesPoint>> = BTreeMap::new();
    for e in events {
        if let Event::Meter(m) = e {
            let m_ts_utc = m.ts.with_timezone(&chrono::Utc);
            if m_ts_utc >= start_window && m_ts_utc <= now_utc {
                for lane in &m.lanes {
                    let remaining_weekly = lane.remaining_weekly.map(clamp_fraction);
                    let point = SeriesPoint {
                        ts: m.ts,
                        remaining_weekly,
                    };
                    if let Some(points) = series.get_mut(&lane.lane) {
                        points.push(point);
                    } else {
                        series.insert(lane.lane.clone(), vec![point]);
                    }
                }
            }
        }
    }

    Snapshot {
        meters,
        threads,
        series,
        cache_age_s,
    }
}

/// Meter names `lanes.tsv` can actually spend. Same mapping as report.py:
/// non-agy harness → harness name; agy gemini-* → agy-gemini; other agy → agy-claude-gpt.
pub fn spendable_meters_from_lanes_tsv(text: &str) -> HashSet<String> {
    let mut out = HashSet::new();
    for line in text.lines() {
        if line.starts_with('#') || line.trim().is_empty() {
            continue;
        }
        let mut cols = line.split('\t');
        let _lane = match cols.next() {
            Some(s) if !s.is_empty() => s,
            _ => continue,
        };
        let harness = match cols.next() {
            Some(s) => s,
            None => continue,
        };
        let slug = match cols.next() {
            Some(s) => s,
            None => continue,
        };
        let meter = if harness != "agy" {
            harness.to_string()
        } else if slug.starts_with("gemini") {
            "agy-gemini".to_string()
        } else {
            "agy-claude-gpt".to_string()
        };
        out.insert(meter);
    }
    out
}

/// Claude session meters stay visible even with no lanes.tsv row. agy-claude-gpt does not:
/// no dispatch lane spends that probe group.
pub fn lane_is_displayed(lane: &Lane, spendable: &HashSet<String>) -> bool {
    spendable.contains(&lane.lane) || lane.harness.as_deref() == Some("claude")
}

/// Drop probe meters no lane can spend, and their burn series. Empty `spendable` means
/// lanes.tsv was not loaded — leave the snapshot alone.
pub fn hide_unspendable(mut snap: Snapshot, spendable: &HashSet<String>) -> Snapshot {
    if spendable.is_empty() {
        return snap;
    }
    snap.meters.retain(|l| lane_is_displayed(l, spendable));
    let keep: HashSet<String> = snap.meters.iter().map(|l| l.lane.clone()).collect();
    snap.series.retain(|name, _| keep.contains(name));
    snap
}

/// One line in the dispatch activity log: in-flight (run/stale) or a finish.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ActivityRow {
    pub ts: DateTime<FixedOffset>,
    pub thread_id: String,
    pub lane: String,
    pub class: Option<String>,
    pub status: String,
    pub secs: u64,
    /// Parent session or worktree the dispatch was launched from.
    pub parent: String,
    /// Short work label from the brief filename.
    pub work: String,
}

/// Brief stem without date prefix or a leading `brief-`.
pub fn work_label(brief: Option<&str>) -> String {
    let Some(p) = brief.filter(|s| !s.is_empty() && *s != "-") else {
        return "—".to_string();
    };
    let name = Path::new(p)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or(p);
    let name = name.strip_prefix("brief-").unwrap_or(name);
    let b = name.as_bytes();
    if name.len() > 11
        && b[4] == b'-'
        && b[7] == b'-'
        && b[10] == b'-'
        && name[..4].bytes().all(|c| c.is_ascii_digit())
        && name[5..7].bytes().all(|c| c.is_ascii_digit())
        && name[8..10].bytes().all(|c| c.is_ascii_digit())
    {
        return name[11..].to_string();
    }
    name.to_string()
}

fn is_session_uuid(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 36
        && b[8] == b'-'
        && b[13] == b'-'
        && b[18] == b'-'
        && b[23] == b'-'
        && s.bytes()
            .enumerate()
            .all(|(i, c)| matches!(i, 8 | 13 | 18 | 23) || c.is_ascii_hexdigit())
}

/// Claude Code scratchpad UUID if present, else the worktree directory name.
pub fn parent_label(brief: Option<&str>, cwd: Option<&str>) -> String {
    if let Some(p) = brief {
        for comp in Path::new(p).components() {
            if let std::path::Component::Normal(s) = comp {
                if let Some(u) = s.to_str() {
                    if is_session_uuid(u) {
                        return u[..8].to_string();
                    }
                }
            }
        }
    }
    if let Some(c) = cwd.filter(|s| !s.is_empty() && *s != "-") {
        if let Some(name) = Path::new(c).file_name().and_then(|s| s.to_str()) {
            if !name.is_empty() {
                return name.to_string();
            }
        }
    }
    "—".to_string()
}

impl ActivityRow {
    pub fn is_live(&self) -> bool {
        matches!(self.status.as_str(), "run" | "stale")
    }
}

/// Newest-first ledger of dispatches. Live threads (run/stale) sort above finished ones.
pub fn activity_log<Tz: TimeZone>(events: &[Event], now: DateTime<Tz>) -> Vec<ActivityRow> {
    let now_utc = now.with_timezone(&chrono::Utc);
    let mut starts: HashMap<&str, &DispatchStartEvent> = HashMap::new();
    let mut finishes: HashMap<&str, &DispatchFinishEvent> = HashMap::new();
    for e in events {
        match e {
            Event::DispatchStart(s) => {
                starts.entry(s.thread_id.as_str()).or_insert(s);
            }
            Event::DispatchFinish(f) => {
                finishes.insert(f.thread_id.as_str(), f);
            }
            _ => {}
        }
    }
    let mut ids: Vec<&str> = starts
        .keys()
        .copied()
        .chain(finishes.keys().copied())
        .collect();
    ids.sort_unstable();
    ids.dedup();

    let mut rows = Vec::with_capacity(ids.len());
    for id in ids {
        if let Some(f) = finishes.get(id) {
            let start = starts.get(id);
            let brief = start.and_then(|s| s.brief.as_deref());
            let cwd = start.and_then(|s| s.cwd.as_deref());
            rows.push(ActivityRow {
                ts: f.ts,
                thread_id: id.to_string(),
                lane: f.lane.clone(),
                class: f
                    .class
                    .clone()
                    .or_else(|| start.and_then(|s| s.class.clone())),
                status: f.status.clone(),
                secs: f.secs,
                parent: parent_label(brief, cwd),
                work: work_label(brief),
            });
        } else if let Some(s) = starts.get(id) {
            let start_utc = s.ts.with_timezone(&chrono::Utc);
            let stale = now_utc > start_utc + Duration::seconds(s.timeout_s as i64);
            let elapsed = now_utc
                .signed_duration_since(start_utc)
                .num_seconds()
                .max(0) as u64;
            let brief = s.brief.as_deref();
            let cwd = s.cwd.as_deref();
            rows.push(ActivityRow {
                ts: s.ts,
                thread_id: id.to_string(),
                lane: s.lane.clone(),
                class: s.class.clone(),
                status: if stale { "stale" } else { "run" }.to_string(),
                secs: elapsed,
                parent: parent_label(brief, cwd),
                work: work_label(brief),
            });
        }
    }
    rows.sort_by(|a, b| b.is_live().cmp(&a.is_live()).then(b.ts.cmp(&a.ts)));
    rows
}
