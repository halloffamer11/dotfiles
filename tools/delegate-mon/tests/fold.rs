use chrono::DateTime;
use delegate_mon::{
    activity_log, clamp_fraction, fold, hide_unspendable, parent_label, parse_event, parse_events,
    spendable_meters_from_lanes_tsv, work_label, Event, Lane, ThreadState, UsageDoc, Window,
};
use std::collections::BTreeMap;
use std::fs;

#[test]
fn test_fixture_a_two_meters_series_has_weekly_not_r() {
    // Spec §5 & Plan Step 3: (a) two meters -> series has weekly, not r
    let content = fs::read_to_string("tests/fixtures/two_meters.jsonl")
        .expect("read fixture two_meters.jsonl");
    let events = parse_events(&content).expect("parse events");
    assert_eq!(events.len(), 2);

    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:35:00-04:00").expect("parse now timestamp");
    let snapshot = fold(&events, None, now, Window::Hour1);

    // Series must use remaining_weekly (0.90 and 0.85), NOT r (0.70 and 0.65)
    let agy_series = snapshot
        .series
        .get("agy-gemini")
        .expect("series for agy-gemini");
    assert_eq!(agy_series.len(), 2);
    assert_eq!(agy_series[0].remaining_weekly, Some(0.90));
    assert_eq!(agy_series[1].remaining_weekly, Some(0.85));

    // Meters falls back to the latest meter event when usage_doc is None
    assert_eq!(snapshot.meters.len(), 1);
    assert_eq!(snapshot.meters[0].lane, "agy-gemini");
    assert_eq!(snapshot.meters[0].remaining_weekly, Some(0.85));
    assert_eq!(snapshot.meters[0].r, Some(0.65));
}

#[test]
fn test_fixture_b_start_without_finish_one_thread() {
    // Spec §5 & Plan Step 3: (b) start without finish -> one thread
    let content = fs::read_to_string("tests/fixtures/start_no_finish.jsonl")
        .expect("read fixture start_no_finish.jsonl");
    let events = parse_events(&content).expect("parse events");
    assert_eq!(events.len(), 1);

    // 4 minutes after start (23:01 -> 23:05), within timeout_s (600s)
    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:05:00-04:00").expect("parse now timestamp");
    let snapshot = fold(&events, None, now, Window::Hour1);

    assert_eq!(snapshot.threads.len(), 1);
    let thread = &snapshot.threads[0];
    assert_eq!(thread.thread_id, "550e8400-e29b-41d4-a716-446655440001");
    assert_eq!(thread.lane, "flash-high@agy");
    assert_eq!(thread.class, Some("verify".to_string()));
    assert_eq!(thread.state, ThreadState::Run);
    assert_eq!(thread.elapsed_s, 240);
}

#[test]
fn test_fixture_c_start_and_finish_zero_threads() {
    // Spec §5 & Plan Step 3: (c) start+finish -> zero threads
    let content = fs::read_to_string("tests/fixtures/start_and_finish.jsonl")
        .expect("read fixture start_and_finish.jsonl");
    let events = parse_events(&content).expect("parse events");
    assert_eq!(events.len(), 2);

    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:05:00-04:00").expect("parse now timestamp");
    let snapshot = fold(&events, None, now, Window::Hour1);

    assert!(
        snapshot.threads.is_empty(),
        "expected 0 threads for matched start and finish"
    );
}

#[test]
fn test_fixture_d_start_timeout_past_that_stale() {
    // Spec §5 & Plan Step 3: (d) start with timeout_s=1 and now past that -> stale
    let content = fs::read_to_string("tests/fixtures/start_timeout.jsonl")
        .expect("read fixture start_timeout.jsonl");
    let events = parse_events(&content).expect("parse events");
    assert_eq!(events.len(), 1);

    // 5 seconds after start, with timeout_s = 1 (deadline was 23:01:01)
    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:01:05-04:00").expect("parse now timestamp");
    let snapshot = fold(&events, None, now, Window::Hour1);

    assert_eq!(snapshot.threads.len(), 1);
    let thread = &snapshot.threads[0];
    assert_eq!(thread.thread_id, "550e8400-e29b-41d4-a716-446655440003");
    assert_eq!(thread.state, ThreadState::Stale);
    assert_eq!(thread.elapsed_s, 5);
}

#[test]
fn test_fixture_e_legacy_hook_ignored_for_threads_and_series() {
    // Spec §5 & Plan Step 3: (e) legacy hook row does not create a thread and does not enter weekly series
    let content = fs::read_to_string("tests/fixtures/legacy_hook.jsonl")
        .expect("read fixture legacy_hook.jsonl");
    let events = parse_events(&content).expect("parse events");
    assert_eq!(events.len(), 1);
    assert!(matches!(&events[0], Event::LegacyHook(_)));

    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:05:00-04:00").expect("parse now timestamp");
    let snapshot = fold(&events, None, now, Window::Hour1);

    assert!(snapshot.threads.is_empty());
    assert!(snapshot.series.is_empty());
    assert!(snapshot.meters.is_empty());
}

#[test]
fn test_clamp_fractions_outside_range() {
    // Spec §5: Clamp remaining fractions (remaining_5h, remaining_weekly, r) to 0..=1 when present
    let content =
        fs::read_to_string("tests/fixtures/clamp.jsonl").expect("read fixture clamp.jsonl");
    let events = parse_events(&content).expect("parse events");
    assert_eq!(events.len(), 1);

    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:05:00-04:00").expect("parse now timestamp");
    let snapshot = fold(&events, None, now, Window::Hour1);

    assert_eq!(snapshot.meters.len(), 1);
    let meter = &snapshot.meters[0];
    assert_eq!(meter.remaining_5h, Some(1.0)); // was 1.25 -> clamped to 1.0
    assert_eq!(meter.remaining_weekly, Some(0.0)); // was -0.10 -> clamped to 0.0
    assert_eq!(meter.r, Some(1.0)); // was 1.50 -> clamped to 1.0

    let series = &snapshot.series["agy-gemini"];
    assert_eq!(series[0].remaining_weekly, Some(0.0));
}

#[test]
fn test_usage_doc_precedence_and_cache_age() {
    // Spec §5: meters from latest usage.json doc if present; cache_age_s = now - probed_at
    let content = fs::read_to_string("tests/fixtures/two_meters.jsonl")
        .expect("read fixture two_meters.jsonl");
    let events = parse_events(&content).expect("parse events");

    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:00:10-04:00").expect("parse now timestamp");
    let now_epoch_s = now.timestamp() as f64;

    let doc = UsageDoc {
        probed_at: now_epoch_s - 42.0,
        probed_at_iso: Some("2026-09-02T22:59:28-04:00".to_string()),
        gate: Some(0.10),
        rollover_min: Some(30),
        lanes: vec![Lane {
            lane: "custom-lane".to_string(),
            harness: Some("custom".to_string()),
            meter: None,
            remaining_5h: Some(0.5),
            remaining_weekly: Some(0.5),
            r: Some(0.5),
            binding: Some("5h".to_string()),
            reset_5h: None,
            reset_weekly: None,
            reset_binding: None,
            cycle_left: None,
            pace: None,
            score: None,
            status: Some("ok".to_string()),
            rollover_soon: Some(false),
            note: None,
        }],
    };

    let snapshot = fold(&events, Some(&doc), now, Window::Hour1);

    // usage.json takes precedence over meter events in the ledger
    assert_eq!(snapshot.meters.len(), 1);
    assert_eq!(snapshot.meters[0].lane, "custom-lane");

    // cache_age_s is calculated correctly
    assert_eq!(snapshot.cache_age_s, Some(42.0));
    assert_eq!(snapshot.cache_age_secs(), Some(42));
}

#[test]
fn test_missing_weekly_is_a_gap_not_r() {
    // Spec §5: Missing weekly is a gap, not r. Do not use hook r
    let line = r#"{"v":1,"kind":"meter","ts":"2026-09-02T23:00:00-04:00","source":"probe","cache_age_s":0,"probed_at":1788403774.3,"lanes":[{"lane":"grok-5h-only","remaining_5h":0.80,"remaining_weekly":null,"r":0.80}]}"#;
    let events = parse_events(line).expect("parse line");

    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:05:00-04:00").expect("parse now timestamp");
    let snapshot = fold(&events, None, now, Window::Hour1);

    let points = &snapshot.series["grok-5h-only"];
    assert_eq!(points.len(), 1);
    // Gap: remaining_weekly is None, NOT fallback to r (0.80)
    assert_eq!(points[0].remaining_weekly, None);
}

#[test]
fn test_duplicate_dispatch_start_keeps_first() {
    let lines = r#"
{"v":1,"kind":"dispatch.start","ts":"2026-09-02T23:01:00-04:00","thread_id":"th-dup","lane":"flash-high@agy","timeout_s":600}
{"v":1,"kind":"dispatch.start","ts":"2026-09-02T23:02:00-04:00","thread_id":"th-dup","lane":"flash-high@agy","timeout_s":600}
"#;
    let events = parse_events(lines).expect("parse events");
    assert_eq!(events.len(), 2);

    let now =
        DateTime::parse_from_rfc3339("2026-09-02T23:05:00-04:00").expect("parse now timestamp");
    let snapshot = fold(&events, None, now, Window::Hour1);

    assert_eq!(snapshot.threads.len(), 1);
    let thread = &snapshot.threads[0];
    assert_eq!(thread.thread_id, "th-dup");
    let expected_start =
        DateTime::parse_from_rfc3339("2026-09-02T23:01:00-04:00").expect("parse ts");
    assert_eq!(thread.start_ts, expected_start);
    assert_eq!(thread.elapsed_s, 240);
}

#[test]
fn test_legacy_hook_requires_absence_of_kind_key() {
    let line_non_string_kind = r#"{"kind":123,"lane":"test"}"#;
    let ev = parse_event(line_non_string_kind).expect("parse line");
    assert!(
        ev.is_none(),
        "expected non-string kind to be treated as unknown and dropped"
    );

    let line_legacy = r#"{"ts":"2026-09-02T23:00:00-04:00","lane":"test","r":0.5}"#;
    let ev_legacy = parse_event(line_legacy).expect("parse line");
    assert!(matches!(ev_legacy, Some(Event::LegacyHook(_))));
}

#[test]
fn test_clamp_negative_zero_normalizes_to_positive_zero() {
    let neg_zero = -0.0f64;
    assert!(neg_zero.is_sign_negative());
    let clamped = clamp_fraction(neg_zero);
    assert_eq!(clamped, 0.0);
    assert!(clamped.is_sign_positive(), "clamped -0.0 must be +0.0");
}

fn lane(name: &str, harness: &str) -> Lane {
    Lane {
        lane: name.to_string(),
        harness: Some(harness.to_string()),
        meter: None,
        remaining_5h: Some(0.5),
        remaining_weekly: Some(0.5),
        r: Some(0.5),
        binding: None,
        reset_5h: None,
        reset_weekly: None,
        reset_binding: None,
        cycle_left: None,
        pace: None,
        score: None,
        status: Some("ok".to_string()),
        rollover_soon: Some(false),
        note: None,
    }
}

#[test]
fn test_agy_claude_gpt_hidden_when_no_lane_spends_it() {
    let tsv = "\
# lane\tharness\tslug\tclasses\tnote
flash-high@agy\tagy\tgemini-3.8-flash-high\timpl\t
grok46@grok\tgrok\tgrok-4.6\timpl\t
terra@codex\tcodex\tgpt-5.6-terra\timpl\t
";
    let spendable = spendable_meters_from_lanes_tsv(tsv);
    assert!(spendable.contains("agy-gemini"));
    assert!(spendable.contains("grok"));
    assert!(spendable.contains("codex"));
    assert!(!spendable.contains("agy-claude-gpt"));

    let mut series = BTreeMap::new();
    series.insert("agy-gemini".to_string(), vec![]);
    series.insert("agy-claude-gpt".to_string(), vec![]);
    series.insert("claude-general".to_string(), vec![]);
    let snap = hide_unspendable(
        delegate_mon::Snapshot {
            meters: vec![
                lane("agy-gemini", "agy"),
                lane("agy-claude-gpt", "agy"),
                lane("claude-general", "claude"),
                lane("grok", "grok"),
            ],
            threads: vec![],
            series,
            cache_age_s: None,
        },
        &spendable,
    );
    let names: Vec<&str> = snap.meters.iter().map(|l| l.lane.as_str()).collect();
    assert_eq!(names, vec!["agy-gemini", "claude-general", "grok"]);
    assert!(!snap.series.contains_key("agy-claude-gpt"));
    assert!(snap.series.contains_key("agy-gemini"));
    assert!(snap.series.contains_key("claude-general"));
}

#[test]
fn test_activity_log_finish_and_live_sort() {
    let finished = fs::read_to_string("tests/fixtures/start_and_finish.jsonl").unwrap();
    let live = fs::read_to_string("tests/fixtures/start_no_finish.jsonl").unwrap();
    let events = parse_events(&format!("{finished}{live}")).unwrap();
    let now = DateTime::parse_from_rfc3339("2026-09-02T23:05:00-04:00").unwrap();
    let rows = activity_log(&events, now);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].status, "run");
    assert_eq!(rows[0].lane, "flash-high@agy");
    assert_eq!(rows[1].status, "done");
    assert_eq!(rows[1].secs, 104);
}

#[test]
fn test_activity_log_stale_after_timeout() {
    let content = fs::read_to_string("tests/fixtures/start_timeout.jsonl").unwrap();
    let events = parse_events(&content).unwrap();
    let now = DateTime::parse_from_rfc3339("2026-09-02T23:01:05-04:00").unwrap();
    let rows = activity_log(&events, now);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].status, "stale");
}

#[test]
fn test_work_and_parent_labels() {
    assert_eq!(
        work_label(Some(
            "/Users/dreiss/.cache/delegate/briefs/2026-09-03-task3-tui.md"
        )),
        "task3-tui"
    );
    assert_eq!(
        work_label(Some("/tmp/scratchpad/brief-ledger14-round5.md")),
        "ledger14-round5"
    );
    assert_eq!(
        work_label(Some("/proj/.scratch/player-data/briefs/04-flex-schema.md")),
        "04-flex-schema"
    );
    assert_eq!(work_label(None), "—");

    let claude_brief = "/private/tmp/claude-501/-Users-dreiss-Documents-daedalus-FFB2/c65906ee-fba1-47d9-bf6d-2f437a2d88e7/scratchpad/brief-15-o.md";
    assert_eq!(
        parent_label(Some(claude_brief), Some("/x/worktrees/overall-focus")),
        "c65906ee"
    );
    assert_eq!(
        parent_label(
            Some("/Users/dreiss/.cache/delegate/briefs/2026-09-03-task3-fix.md"),
            Some("/Users/dreiss/.cache/delegate/wt-monitor-t3")
        ),
        "wt-monitor-t3"
    );
}
