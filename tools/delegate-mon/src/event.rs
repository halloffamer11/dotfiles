use chrono::{DateTime, FixedOffset};
use serde::{Deserialize, Deserializer, Serialize};

/// Per-lane quota and status information from `usage.json` or `meter` events.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Lane {
    pub lane: String,
    #[serde(default)]
    pub harness: Option<String>,
    #[serde(default)]
    pub meter: Option<String>,
    #[serde(default)]
    pub remaining_5h: Option<f64>,
    #[serde(default)]
    pub remaining_weekly: Option<f64>,
    #[serde(default)]
    pub r: Option<f64>,
    #[serde(default)]
    pub binding: Option<String>,
    #[serde(default)]
    pub reset_5h: Option<f64>,
    #[serde(default)]
    pub reset_weekly: Option<f64>,
    #[serde(default)]
    pub reset_binding: Option<f64>,
    #[serde(default)]
    pub cycle_left: Option<f64>,
    #[serde(default)]
    pub pace: Option<f64>,
    #[serde(default)]
    pub score: Option<f64>,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub rollover_soon: Option<bool>,
    #[serde(default)]
    pub note: Option<String>,
}

/// Meter event emitted by `usage.py` on cache write (probe path).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MeterEvent {
    pub v: u32,
    pub kind: String,
    pub ts: DateTime<FixedOffset>,
    #[serde(default)]
    pub source: Option<String>,
    #[serde(default)]
    pub cache_age_s: Option<f64>,
    #[serde(default)]
    pub probed_at: Option<f64>,
    #[serde(default)]
    pub lanes: Vec<Lane>,
}

/// Dispatch start event emitted by `dispatch.sh` before spawning a child process.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DispatchStartEvent {
    pub v: u32,
    pub kind: String,
    pub ts: DateTime<FixedOffset>,
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
}

/// Dispatch finish event emitted once per dispatch upon completion or failure.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DispatchFinishEvent {
    pub v: u32,
    pub kind: String,
    pub ts: DateTime<FixedOffset>,
    pub thread_id: String,
    pub lane: String,
    #[serde(default)]
    pub class: Option<String>,
    pub secs: u64,
    pub rc: i32,
    pub status: String,
    #[serde(default)]
    pub child_session: Option<String>,
    #[serde(default)]
    pub out: Option<String>,
}

/// Legacy hook row emitted by earlier Claude hooks, without version or kind fields.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LegacyHookEvent {
    #[serde(default)]
    pub ts: Option<DateTime<FixedOffset>>,
    #[serde(default)]
    pub lane: Option<String>,
    #[serde(default)]
    pub r: Option<f64>,
    // Flatten arbitrary extra fields so legacy records never fail parsing
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

/// Parsed event from the ledger. Unknown kinds are preserved as `Unknown` and ignored by fold.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(untagged)]
pub enum Event {
    Meter(MeterEvent),
    DispatchStart(DispatchStartEvent),
    DispatchFinish(DispatchFinishEvent),
    LegacyHook(LegacyHookEvent),
    Unknown,
}

impl<'de> Deserialize<'de> for Event {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = serde_json::Value::deserialize(deserializer)?;
        let obj = match value.as_object() {
            Some(map) => map,
            None => return Ok(Event::Unknown),
        };

        let has_v = obj.contains_key("v");
        let has_kind = obj.contains_key("kind");
        let kind = obj.get("kind").and_then(|k| k.as_str());

        if !has_v && !has_kind {
            let legacy: LegacyHookEvent =
                serde_json::from_value(value).map_err(serde::de::Error::custom)?;
            return Ok(Event::LegacyHook(legacy));
        }

        match kind {
            Some("meter") => {
                let ev: MeterEvent =
                    serde_json::from_value(value).map_err(serde::de::Error::custom)?;
                Ok(Event::Meter(ev))
            }
            Some("dispatch.start") => {
                let ev: DispatchStartEvent =
                    serde_json::from_value(value).map_err(serde::de::Error::custom)?;
                Ok(Event::DispatchStart(ev))
            }
            Some("dispatch.finish") => {
                let ev: DispatchFinishEvent =
                    serde_json::from_value(value).map_err(serde::de::Error::custom)?;
                Ok(Event::DispatchFinish(ev))
            }
            Some(_) => Ok(Event::Unknown),
            None => Ok(Event::Unknown),
        }
    }
}

/// Parsed `usage.json` document.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UsageDoc {
    pub probed_at: f64,
    #[serde(default)]
    pub probed_at_iso: Option<String>,
    #[serde(default)]
    pub gate: Option<f64>,
    #[serde(default)]
    pub rollover_min: Option<u64>,
    #[serde(default)]
    pub lanes: Vec<Lane>,
}

#[derive(Debug, thiserror::Error)]
pub enum EventError {
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

/// Parses a single line from JSONL. Returns None for empty lines or unknown kinds.
pub fn parse_event(line: &str) -> Result<Option<Event>, EventError> {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }
    let ev: Event = serde_json::from_str(trimmed)?;
    if matches!(ev, Event::Unknown) {
        Ok(None)
    } else {
        Ok(Some(ev))
    }
}

/// Parses multiple JSONL lines, dropping empty lines and unknown kinds.
pub fn parse_events(input: &str) -> Result<Vec<Event>, EventError> {
    let mut events = Vec::new();
    for line in input.lines() {
        if let Some(ev) = parse_event(line)? {
            events.push(ev);
        }
    }
    Ok(events)
}
