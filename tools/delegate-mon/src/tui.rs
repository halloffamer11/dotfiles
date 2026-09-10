use std::collections::HashSet;
use std::fs::File;
use std::io::{BufRead, BufReader, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Sender};
use std::time::Duration;

use chrono::{Local, TimeZone};
use crossterm::event::{self, Event as CrosstermEvent, KeyCode, KeyEvent};
use ratatui::{
    backend::Backend,
    layout::{Constraint, Layout, Rect},
    style::{Color, Modifier, Style},
    symbols,
    text::{Line, Span},
    widgets::{
        Axis, Block, BorderType, Cell, Chart, Clear, Dataset, GraphType, LegendPosition, LineGauge,
        Paragraph, Row, Table, TableState,
    },
    Frame, Terminal,
};

use crate::event::{parse_event, Event, UsageDoc};
use crate::store::{
    activity_log, clamp_fraction, fold, hide_unspendable, spendable_meters_from_lanes_tsv,
    ActivityRow, Snapshot, Window,
};

pub const RANK_CLASSES: &[&str] = &[
    "impl",
    "verify",
    "review",
    "scout",
    "hard-impl",
    "mechanical",
];

#[derive(Debug)]
pub enum Message {
    Key(KeyEvent),
    FileChanged,
    ProbeDone(Result<(), String>),
    RankDone {
        class: &'static str,
        result: Result<String, String>,
    },
    Tick,
    Quit,
}

pub fn resolve_ledger_path() -> PathBuf {
    if let Ok(p) = std::env::var("DELEGATE_LEDGER") {
        PathBuf::from(p)
    } else if let Ok(home) = std::env::var("HOME") {
        PathBuf::from(home).join(".cache/delegate/ledger.jsonl")
    } else {
        PathBuf::from(".cache/delegate/ledger.jsonl")
    }
}

pub fn resolve_cache_path() -> PathBuf {
    if let Ok(p) = std::env::var("DELEGATE_CACHE") {
        PathBuf::from(p)
    } else if let Ok(p) = std::env::var("CONSULT_CACHE") {
        PathBuf::from(p)
    } else if let Ok(home) = std::env::var("HOME") {
        PathBuf::from(home).join(".cache/delegate/usage.json")
    } else {
        PathBuf::from(".cache/delegate/usage.json")
    }
}

pub fn resolve_script(script_name: &str) -> PathBuf {
    if let Ok(skill_dir) = std::env::var("DELEGATE_SKILL") {
        let p = PathBuf::from(skill_dir).join(script_name);
        if p.exists() {
            return p;
        }
    }
    let parent_p = PathBuf::from("..").join(script_name);
    if parent_p.exists() {
        return parent_p;
    }
    let cur_p = PathBuf::from(script_name);
    if cur_p.exists() {
        return cur_p;
    }
    PathBuf::from("..").join(script_name)
}

pub fn spawn_refresh(tx: Sender<Message>) {
    let script = resolve_script("usage.py");
    std::thread::spawn(move || {
        let res = std::process::Command::new("python3")
            .arg(&script)
            .arg("--refresh")
            .output();
        let msg = match res {
            Ok(o) if o.status.success() => Ok(()),
            Ok(o) => Err(String::from_utf8_lossy(&o.stderr).to_string()),
            Err(e) => Err(e.to_string()),
        };
        let _ = tx.send(Message::ProbeDone(msg));
    });
}

pub fn spawn_rank(tx: Sender<Message>, class: &'static str) {
    let script = resolve_script("rank.py");
    std::thread::spawn(move || {
        let res = std::process::Command::new("python3")
            .arg(&script)
            .arg(class)
            .output();
        let msg = match res {
            Ok(o) if o.status.success() => {
                let stdout = String::from_utf8_lossy(&o.stdout).to_string();
                Ok(stdout)
            }
            Ok(o) => {
                let stderr = String::from_utf8_lossy(&o.stderr).to_string();
                let stdout = String::from_utf8_lossy(&o.stdout).to_string();
                if !stdout.is_empty() {
                    Ok(stdout)
                } else {
                    Err(stderr)
                }
            }
            Err(e) => Err(e.to_string()),
        };
        let _ = tx.send(Message::RankDone { class, result: msg });
    });
}

pub struct Model {
    pub ledger_path: PathBuf,
    pub cache_path: PathBuf,
    pub spendable: HashSet<String>,
    pub ledger_offset: u64,
    pub events: Vec<Event>,
    pub usage_doc: Option<UsageDoc>,
    pub snapshot: Snapshot,
    pub activity: Vec<ActivityRow>,
    pub window: Window,
    pub thread_state: TableState,
    pub refresh_in_flight: bool,
    pub rank_in_flight: bool,
    pub rank_open: bool,
    pub rank_class_idx: usize,
    pub rank_output: Option<String>,
}

impl Model {
    pub fn new() -> Self {
        let ledger_path = resolve_ledger_path();
        let cache_path = resolve_cache_path();

        let usage_doc = if cache_path.exists() {
            std::fs::read_to_string(&cache_path)
                .ok()
                .and_then(|s| serde_json::from_str::<UsageDoc>(&s).ok())
        } else {
            None
        };

        let mut events = Vec::new();
        let mut ledger_offset = 0;
        if ledger_path.exists() {
            if let Ok(file) = File::open(&ledger_path) {
                let mut reader = BufReader::new(file);
                let mut line = String::new();
                while let Ok(n) = reader.read_line(&mut line) {
                    if n == 0 {
                        break;
                    }
                    if !line.ends_with('\n') {
                        break;
                    }
                    if let Ok(Some(ev)) = parse_event(&line) {
                        events.push(ev);
                    }
                    ledger_offset += n as u64;
                    line.clear();
                }
            }
        }

        let spendable = std::fs::read_to_string(resolve_script("lanes.tsv"))
            .map(|s| spendable_meters_from_lanes_tsv(&s))
            .unwrap_or_default();

        let window = Window::Hour1;
        let now = Local::now();
        let snapshot = hide_unspendable(fold(&events, usage_doc.as_ref(), now, window), &spendable);
        let activity = activity_log(&events, now);
        let mut thread_state = TableState::default();
        if !activity.is_empty() {
            thread_state.select(Some(0));
        }

        Self {
            ledger_path,
            cache_path,
            spendable,
            ledger_offset,
            events,
            usage_doc,
            snapshot,
            activity,
            window,
            thread_state,
            refresh_in_flight: false,
            rank_in_flight: false,
            rank_open: false,
            rank_class_idx: 0,
            rank_output: None,
        }
    }

    pub fn reload_cache(&mut self) {
        if self.cache_path.exists() {
            if let Ok(content) = std::fs::read_to_string(&self.cache_path) {
                if let Ok(doc) = serde_json::from_str::<UsageDoc>(&content) {
                    self.usage_doc = Some(doc);
                }
            }
        }
    }

    pub fn tail_ledger(&mut self) {
        if !self.ledger_path.exists() {
            return;
        }
        if let Ok(metadata) = std::fs::metadata(&self.ledger_path) {
            let file_len = metadata.len();
            if file_len < self.ledger_offset {
                self.ledger_offset = 0;
                self.events.clear();
            }
            if let Ok(mut file) = File::open(&self.ledger_path) {
                if file.seek(SeekFrom::Start(self.ledger_offset)).is_ok() {
                    let mut reader = BufReader::new(file);
                    let mut line = String::new();
                    while let Ok(n) = reader.read_line(&mut line) {
                        if n == 0 {
                            break;
                        }
                        if !line.ends_with('\n') {
                            break;
                        }
                        if let Ok(Some(ev)) = parse_event(&line) {
                            self.events.push(ev);
                        }
                        self.ledger_offset += n as u64;
                        line.clear();
                    }
                }
            }
        }
    }

    pub fn refold(&mut self) {
        let now = Local::now();
        self.snapshot = hide_unspendable(
            fold(&self.events, self.usage_doc.as_ref(), now, self.window),
            &self.spendable,
        );
        self.activity = activity_log(&self.events, now);
        let count = self.activity.len();
        if count == 0 {
            self.thread_state.select(None);
        } else if let Some(sel) = self.thread_state.selected() {
            if sel >= count {
                self.thread_state.select(Some(count - 1));
            }
        } else {
            self.thread_state.select(Some(0));
        }
    }
}

impl Default for Model {
    fn default() -> Self {
        Self::new()
    }
}

fn format_cache_age(cache_age_s: Option<f64>) -> String {
    match cache_age_s {
        Some(s) if s < 60.0 => format!("cache {}s", s.round() as u64),
        Some(s) => format!("cache {}m", (s / 60.0).round() as u64),
        None => "cache —".to_string(),
    }
}

fn format_display_path(p: &Path) -> String {
    if let Ok(home) = std::env::var("HOME") {
        let home_path = Path::new(&home);
        if let Ok(stripped) = p.strip_prefix(home_path) {
            return format!("~/{}", stripped.display());
        }
    }
    p.display().to_string()
}

fn color_for_ratio(ratio: f64) -> Color {
    if ratio < 0.10 {
        Color::Red
    } else if ratio < 0.40 {
        Color::Yellow
    } else {
        Color::Green
    }
}

pub fn draw(f: &mut Frame, model: &mut Model) {
    let main_layout = Layout::vertical([
        Constraint::Length(1),
        Constraint::Fill(1),
        Constraint::Fill(1),
        Constraint::Length(2),
    ])
    .split(f.area());

    draw_header(f, main_layout[0], model);

    let middle_layout =
        Layout::horizontal([Constraint::Fill(1), Constraint::Length(68)]).split(main_layout[1]);

    draw_meters(f, middle_layout[0], model);
    draw_activity(f, middle_layout[1], model);

    draw_burn(f, main_layout[2], model);
    draw_footer(f, main_layout[3], model);

    if model.rank_open {
        draw_rank_overlay(f, f.area(), model);
    }
}

fn draw_header(f: &mut Frame, area: Rect, model: &Model) {
    let app_title = "delegate-mon  v0";
    let cache_str = format_cache_age(model.snapshot.cache_age_s);
    let time_str = Local::now().format("%Y-%m-%d %H:%M").to_string();
    let ledger_str = format!("JSONL {}", format_display_path(&model.ledger_path));

    let sep = Span::styled("  |  ", Style::default().add_modifier(Modifier::DIM));
    let line = Line::from(vec![
        Span::styled(app_title, Style::default().add_modifier(Modifier::BOLD)),
        sep.clone(),
        Span::raw(cache_str),
        sep.clone(),
        Span::raw(time_str),
        sep,
        Span::styled(ledger_str, Style::default().add_modifier(Modifier::DIM)),
    ]);

    f.render_widget(Paragraph::new(line), area);
}

const METER_BAR_COLS: u16 = 10;

fn pct_span(ratio: Option<f64>) -> Span<'static> {
    match ratio {
        None => Span::styled("  —", Style::default().add_modifier(Modifier::DIM)),
        Some(r) => {
            let c = clamp_fraction(r);
            Span::styled(
                format!("{:>3}%", (c * 100.0).round() as i64),
                Style::default()
                    .fg(color_for_ratio(c))
                    .add_modifier(Modifier::BOLD),
            )
        }
    }
}

fn render_meter_bar(f: &mut Frame, bar: Rect, pct: Rect, ratio: Option<f64>) {
    f.render_widget(Paragraph::new(pct_span(ratio)), pct);
    match ratio {
        Some(r) => {
            let c = clamp_fraction(r);
            let gauge = LineGauge::default()
                .ratio(c)
                .label("")
                .filled_style(Style::default().fg(color_for_ratio(c)))
                .unfilled_style(Style::default().fg(Color::DarkGray));
            f.render_widget(gauge, bar);
        }
        None => {
            f.render_widget(
                Paragraph::new(Span::styled(
                    "—",
                    Style::default().add_modifier(Modifier::DIM),
                )),
                bar,
            );
        }
    }
}

fn draw_meters(f: &mut Frame, area: Rect, model: &Model) {
    let block = Block::bordered()
        .title(" meters ")
        .border_type(BorderType::Rounded);
    let inner = block.inner(area);
    f.render_widget(block, area);

    let lanes = &model.snapshot.meters;
    for (i, lane) in lanes.iter().enumerate() {
        let lane_y = inner.y + i as u16 * 2;
        if lane_y + 1 >= inner.bottom() {
            break;
        }

        let line1_rect = Rect {
            x: inner.x,
            y: lane_y,
            width: inner.width,
            height: 1,
        };
        let line2_rect = Rect {
            x: inner.x,
            y: lane_y + 1,
            width: inner.width,
            height: 1,
        };

        // name  5h [short bar]  92%  wk [short bar]  74%   leftover unused
        let chunks = Layout::horizontal([
            Constraint::Length(16),
            Constraint::Length(3),
            Constraint::Length(METER_BAR_COLS),
            Constraint::Length(4),
            Constraint::Length(4),
            Constraint::Length(METER_BAR_COLS),
            Constraint::Length(4),
            Constraint::Min(0),
        ])
        .split(line1_rect);

        f.render_widget(
            Paragraph::new(Span::styled(
                &lane.lane,
                Style::default().add_modifier(Modifier::BOLD),
            )),
            chunks[0],
        );
        f.render_widget(
            Paragraph::new(Span::styled(
                "5h ",
                Style::default().add_modifier(Modifier::DIM),
            )),
            chunks[1],
        );
        render_meter_bar(f, chunks[2], chunks[3], lane.remaining_5h);
        f.render_widget(
            Paragraph::new(Span::styled(
                " wk ",
                Style::default().add_modifier(Modifier::DIM),
            )),
            chunks[4],
        );
        render_meter_bar(f, chunks[5], chunks[6], lane.remaining_weekly);

        let dim = Style::default().add_modifier(Modifier::DIM);
        let mut spans = vec![Span::raw("                ")];
        spans.push(Span::styled("bind ", dim));
        spans.push(Span::raw(format!(
            "{:<7}",
            lane.binding.as_deref().unwrap_or("—")
        )));
        spans.push(Span::styled("reset ", dim));
        let reset_str = if let Some(rb) = lane.reset_binding {
            if let Some(dt) = Local.timestamp_opt(rb as i64, 0).single() {
                if lane.binding.as_deref() == Some("5h") {
                    dt.format("%H:%M").to_string()
                } else {
                    dt.format("%b %-d").to_string()
                }
            } else {
                "—".to_string()
            }
        } else {
            "—".to_string()
        };
        spans.push(Span::raw(format!("{:<7}", reset_str)));
        spans.push(Span::styled("pace ", dim));
        if let Some(p) = lane.pace {
            spans.push(Span::raw(format!("{:.2} ", p)));
            if p > 1.0 {
                spans.push(Span::styled("ahead", Style::default().fg(Color::Green)));
            } else {
                spans.push(Span::styled("behind", dim));
            }
        } else {
            spans.push(Span::styled("—", dim));
        }

        f.render_widget(Paragraph::new(Line::from(spans)), line2_rect);
    }
}

fn status_style(status: &str) -> Style {
    match status {
        "done" => Style::default().fg(Color::Green),
        "run" => Style::default()
            .fg(Color::Cyan)
            .add_modifier(Modifier::BOLD),
        "stale" | "partial" => Style::default().fg(Color::Yellow),
        "blocked" => Style::default().fg(Color::Red),
        _ => Style::default().add_modifier(Modifier::DIM),
    }
}

fn format_elapsed(secs: u64) -> String {
    format!("{}:{:02}", secs / 60, secs % 60)
}

fn clip(s: &str, n: usize) -> String {
    if s.chars().count() <= n {
        s.to_string()
    } else {
        s.chars().take(n).collect()
    }
}

fn draw_activity(f: &mut Frame, area: Rect, model: &mut Model) {
    let live = model.activity.iter().filter(|r| r.is_live()).count();
    let title = if live == 0 {
        " activity ".to_string()
    } else {
        format!(" activity  {live} run ")
    };
    let block = Block::bordered()
        .title(title)
        .border_type(BorderType::Rounded);

    if model.activity.is_empty() {
        let text = vec![
            Line::from(Span::styled(
                "when  parent    work            lane             st",
                Style::default().add_modifier(Modifier::BOLD),
            )),
            Line::from(Span::styled(
                "— none —",
                Style::default().add_modifier(Modifier::DIM),
            )),
            Line::from(Span::styled(
                "start/finish lines from dispatch.sh",
                Style::default().add_modifier(Modifier::DIM),
            )),
        ];
        f.render_widget(Paragraph::new(text).block(block), area);
        return;
    }

    let header = Row::new(vec!["when", "parent", "work", "lane", "st", "time"])
        .style(Style::default().add_modifier(Modifier::BOLD));
    let widths = [
        Constraint::Length(5),
        Constraint::Length(8),
        Constraint::Length(16),
        Constraint::Length(16),
        Constraint::Length(7),
        Constraint::Length(6),
    ];
    let rows: Vec<Row> = model
        .activity
        .iter()
        .map(|r| {
            let when = r.ts.format("%H:%M").to_string();
            Row::new(vec![
                Cell::from(when),
                Cell::from(clip(&r.parent, 8)),
                Cell::from(clip(&r.work, 16)),
                Cell::from(clip(&r.lane, 16)),
                Cell::from(r.status.clone()).style(status_style(&r.status)),
                Cell::from(format_elapsed(r.secs)),
            ])
        })
        .collect();

    let table = Table::new(rows, widths)
        .block(block)
        .header(header)
        .row_highlight_style(Style::default().add_modifier(Modifier::REVERSED));
    f.render_stateful_widget(table, area, &mut model.thread_state);
}

fn draw_burn(f: &mut Frame, area: Rect, model: &Model) {
    let window_title = match model.window {
        Window::Hour1 => "[1h]  24h   7d",
        Window::Hour24 => " 1h  [24h]  7d",
        Window::Day7 => " 1h   24h  [7d]",
    };
    let block = Block::bordered()
        .title(format!(" burn  remaining weekly %   {} ", window_title))
        .border_type(BorderType::Rounded);

    let now_epoch = Local::now().timestamp() as f64;
    let window_sec = model.window.duration().num_seconds() as f64;
    let x_min = now_epoch - window_sec;
    let x_max = now_epoch;

    let colors = [
        Color::Cyan,
        Color::Magenta,
        Color::Yellow,
        Color::Green,
        Color::Blue,
        Color::White,
        Color::LightRed,
        Color::LightCyan,
    ];

    let mut series_data: Vec<Vec<(f64, f64)>> = Vec::new();
    let mut lane_names: Vec<String> = Vec::new();
    let mut lane_colors: Vec<Color> = Vec::new();

    for (idx, (lane, points)) in model.snapshot.series.iter().enumerate() {
        let pts: Vec<(f64, f64)> = points
            .iter()
            .filter_map(|p| {
                p.remaining_weekly
                    .map(|rw| (p.ts.timestamp() as f64, rw * 100.0))
            })
            .collect();
        series_data.push(pts);
        lane_names.push(lane.clone());
        lane_colors.push(colors[idx % colors.len()]);
    }

    let datasets: Vec<Dataset> = series_data
        .iter()
        .enumerate()
        .map(|(i, pts)| {
            Dataset::default()
                .name(lane_names[i].as_str())
                .marker(symbols::Marker::Braille)
                .graph_type(GraphType::Line)
                .style(Style::default().fg(lane_colors[i]))
                .data(pts)
        })
        .collect();

    let step = (x_max - x_min) / 4.0;
    let x_labels: Vec<Span> = (0..=4)
        .map(|i| {
            let t = x_min + i as f64 * step;
            if let Some(dt) = Local.timestamp_opt(t as i64, 0).single() {
                let s = if model.window == Window::Day7 {
                    dt.format("%b %d").to_string()
                } else {
                    dt.format("%H:%M").to_string()
                };
                Span::raw(s)
            } else {
                Span::raw("")
            }
        })
        .collect();

    let y_labels = vec![
        Span::raw("0"),
        Span::raw("25"),
        Span::raw("50"),
        Span::raw("75"),
        Span::raw("100"),
    ];

    let x_axis = Axis::default().bounds([x_min, x_max]).labels(x_labels);
    let y_axis = Axis::default().bounds([0.0, 100.0]).labels(y_labels);

    let chart = Chart::new(datasets)
        .block(block)
        .x_axis(x_axis)
        .y_axis(y_axis)
        .legend_position(Some(LegendPosition::TopRight))
        .hidden_legend_constraints((Constraint::Ratio(1, 2), Constraint::Ratio(1, 2)));

    f.render_widget(chart, area);
}

fn draw_footer(f: &mut Frame, area: Rect, model: &Model) {
    let refresh_status = if model.refresh_in_flight { "yes" } else { "no" };
    let rank_status = if model.rank_in_flight {
        " [rank in flight]"
    } else {
        ""
    };
    let key_help = format!(
        "  r refresh (in flight: {})   k rank overlay{}   1/2/3 burn window   j/↑ activity   q quit",
        refresh_status, rank_status
    );

    let line2 = Line::from(vec![
        Span::raw("  thresholds  remaining: "),
        Span::styled("green ≥40%  ", Style::default().fg(Color::Green)),
        Span::styled("yellow 10–40%  ", Style::default().fg(Color::Yellow)),
        Span::styled("red <10% (GATE)     ", Style::default().fg(Color::Red)),
        Span::raw("pace: "),
        Span::styled("green >1.0 ahead", Style::default().fg(Color::Green)),
        Span::styled(
            ", else behind",
            Style::default().add_modifier(Modifier::DIM),
        ),
    ]);

    let paragraph = Paragraph::new(vec![Line::from(key_help), line2]);
    f.render_widget(paragraph, area);
}

fn draw_rank_overlay(f: &mut Frame, area: Rect, model: &Model) {
    let class = RANK_CLASSES[model.rank_class_idx];

    let popup_width = 72.min(area.width.saturating_sub(4));
    let popup_height = 14.min(area.height.saturating_sub(4));
    let popup_x = area.x + (area.width.saturating_sub(popup_width)) / 2;
    let popup_y = area.y + (area.height.saturating_sub(popup_height)) / 2;
    let popup_area = Rect {
        x: popup_x,
        y: popup_y,
        width: popup_width,
        height: popup_height,
    };

    f.render_widget(Clear, popup_area);

    let title = format!(" rank {} (Tab: cycle, k/Esc: close) ", class);
    let block = Block::bordered()
        .title(title)
        .border_type(BorderType::Rounded);

    let mut rows = Vec::new();

    if model.rank_in_flight && model.rank_output.is_none() {
        rows.push(Row::new(vec![
            Cell::from("ranking in flight...").style(Style::default().fg(Color::Yellow))
        ]));
    } else if let Some(ref output) = model.rank_output {
        for line in output.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }
            rows.push(Row::new(vec![Cell::from(line.to_string())]));
        }
        if rows.is_empty() {
            rows.push(Row::new(vec![Cell::from("No ranking available")
                .style(Style::default().add_modifier(Modifier::DIM))]));
        }
    } else {
        rows.push(Row::new(vec![Cell::from(
            "Press Tab to cycle class, k/Esc to close",
        )
        .style(Style::default().add_modifier(Modifier::DIM))]));
    }

    rows.push(Row::new(vec![Cell::from("")]));
    rows.push(Row::new(vec![Cell::from(
        "(display only. TUI does not dispatch.)",
    )
    .style(Style::default().add_modifier(Modifier::DIM))]));

    let table = Table::new(rows, [Constraint::Fill(1)]).block(block);
    f.render_widget(table, popup_area);
}

pub fn run<B: Backend>(terminal: &mut Terminal<B>) -> Result<(), Box<dyn std::error::Error>>
where
    <B as Backend>::Error: 'static,
{
    let (tx, rx) = mpsc::channel::<Message>();

    let tx_keys = tx.clone();
    std::thread::spawn(move || loop {
        match event::read() {
            Ok(CrosstermEvent::Key(key)) => {
                if tx_keys.send(Message::Key(key)).is_err() {
                    break;
                }
            }
            Ok(CrosstermEvent::Resize(..)) => {
                if tx_keys.send(Message::Tick).is_err() {
                    break;
                }
            }
            Ok(_) => {}
            Err(_) => break,
        }
    });

    let tx_tick = tx.clone();
    let ledger_p = resolve_ledger_path();
    let cache_p = resolve_cache_path();
    std::thread::spawn(move || {
        let mut last_ledger_meta = std::fs::metadata(&ledger_p)
            .ok()
            .map(|m| (m.len(), m.modified().ok()));
        let mut last_cache_meta = std::fs::metadata(&cache_p)
            .ok()
            .map(|m| (m.len(), m.modified().ok()));

        loop {
            std::thread::sleep(Duration::from_millis(250));

            let cur_ledger_meta = std::fs::metadata(&ledger_p)
                .ok()
                .map(|m| (m.len(), m.modified().ok()));
            let cur_cache_meta = std::fs::metadata(&cache_p)
                .ok()
                .map(|m| (m.len(), m.modified().ok()));

            if cur_ledger_meta != last_ledger_meta || cur_cache_meta != last_cache_meta {
                last_ledger_meta = cur_ledger_meta;
                last_cache_meta = cur_cache_meta;
                if tx_tick.send(Message::FileChanged).is_err() {
                    break;
                }
            } else if tx_tick.send(Message::Tick).is_err() {
                break;
            }
        }
    });

    let mut model = Model::new();

    terminal.draw(|f| draw(f, &mut model))?;

    while let Ok(msg) = rx.recv() {
        match msg {
            Message::Quit => break,
            Message::Tick => {
                model.refold();
            }
            Message::FileChanged => {
                model.reload_cache();
                model.tail_ledger();
                model.refold();
            }
            Message::ProbeDone(result) => {
                model.refresh_in_flight = false;
                if result.is_ok() {
                    model.reload_cache();
                    model.tail_ledger();
                    model.refold();
                }
            }
            Message::RankDone { class, result } => {
                if class == RANK_CLASSES[model.rank_class_idx] {
                    model.rank_in_flight = false;
                    model.rank_output = Some(match result {
                        Ok(stdout) => stdout,
                        Err(stderr) => format!("Error running rank.py: {stderr}"),
                    });
                }
            }
            Message::Key(key) => {
                if key.kind != event::KeyEventKind::Press {
                    continue;
                }
                match key.code {
                    KeyCode::Char('q') => break,
                    KeyCode::Char('r') => {
                        if !model.refresh_in_flight {
                            model.refresh_in_flight = true;
                            spawn_refresh(tx.clone());
                        }
                    }
                    KeyCode::Char('k') => {
                        if model.rank_open {
                            model.rank_open = false;
                        } else {
                            model.rank_open = true;
                            model.rank_in_flight = true;
                            model.rank_output = None;
                            spawn_rank(tx.clone(), RANK_CLASSES[model.rank_class_idx]);
                        }
                    }
                    KeyCode::Esc => {
                        if model.rank_open {
                            model.rank_open = false;
                        }
                    }
                    KeyCode::Tab => {
                        if model.rank_open {
                            model.rank_class_idx = (model.rank_class_idx + 1) % RANK_CLASSES.len();
                            model.rank_in_flight = true;
                            model.rank_output = None;
                            spawn_rank(tx.clone(), RANK_CLASSES[model.rank_class_idx]);
                        }
                    }
                    KeyCode::Char('1') => {
                        model.window = Window::Hour1;
                        model.refold();
                    }
                    KeyCode::Char('2') => {
                        model.window = Window::Hour24;
                        model.refold();
                    }
                    KeyCode::Char('3') => {
                        model.window = Window::Day7;
                        model.refold();
                    }
                    KeyCode::Char('j') | KeyCode::Down => {
                        let count = model.activity.len();
                        if count > 0 {
                            let next = match model.thread_state.selected() {
                                Some(i) => {
                                    if i + 1 < count {
                                        i + 1
                                    } else {
                                        0
                                    }
                                }
                                None => 0,
                            };
                            model.thread_state.select(Some(next));
                        }
                    }
                    KeyCode::Up => {
                        let count = model.activity.len();
                        if count > 0 {
                            let prev = match model.thread_state.selected() {
                                Some(i) => {
                                    if i > 0 {
                                        i - 1
                                    } else {
                                        count - 1
                                    }
                                }
                                None => 0,
                            };
                            model.thread_state.select(Some(prev));
                        }
                    }
                    _ => {}
                }
            }
        }

        terminal.draw(|f| draw(f, &mut model))?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn test_tail_ledger_unterminated_line() {
        let temp_dir = std::env::temp_dir().join(format!("delegate_test_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&temp_dir);
        let ledger_path = temp_dir.join("ledger.jsonl");

        let line1 = "{\"v\":1,\"ts\":\"2026-09-02T23:00:00-04:00\",\"kind\":\"dispatch.start\",\"thread_id\":\"t1\",\"lane\":\"l1\",\"timeout_s\":600}\n";
        let partial_line2 = "{\"v\":1,\"ts\":\"2026-09-02T23:01:00-04:00\",\"kind\":\"dispatch.st";

        {
            let mut f = File::create(&ledger_path).expect("create test ledger");
            f.write_all(line1.as_bytes()).expect("write line1");
            f.write_all(partial_line2.as_bytes())
                .expect("write partial line2");
        }

        let mut model = Model {
            ledger_path: ledger_path.clone(),
            cache_path: temp_dir.join("usage.json"),
            spendable: HashSet::new(),
            ledger_offset: 0,
            events: Vec::new(),
            usage_doc: None,
            snapshot: fold(&[], None, Local::now(), Window::Hour1),
            activity: Vec::new(),
            window: Window::Hour1,
            thread_state: TableState::default(),
            refresh_in_flight: false,
            rank_in_flight: false,
            rank_open: false,
            rank_class_idx: 0,
            rank_output: None,
        };

        model.tail_ledger();

        assert_eq!(model.events.len(), 1);
        assert_eq!(model.ledger_offset, line1.len() as u64);

        // Now append the rest of line 2 with newline
        let rest_line2 = "art\",\"thread_id\":\"t2\",\"lane\":\"l2\",\"timeout_s\":600}\n";
        {
            let mut f = std::fs::OpenOptions::new()
                .append(true)
                .open(&ledger_path)
                .expect("open test ledger for append");
            f.write_all(rest_line2.as_bytes()).expect("append rest");
        }

        model.tail_ledger();

        assert_eq!(model.events.len(), 2);
        assert_eq!(
            model.ledger_offset,
            (line1.len() + partial_line2.len() + rest_line2.len()) as u64
        );

        let _ = std::fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_rank_done_matching_class() {
        let mut model = Model {
            ledger_path: PathBuf::from("nonexistent"),
            cache_path: PathBuf::from("nonexistent"),
            spendable: HashSet::new(),
            ledger_offset: 0,
            events: Vec::new(),
            usage_doc: None,
            snapshot: fold(&[], None, Local::now(), Window::Hour1),
            activity: Vec::new(),
            window: Window::Hour1,
            thread_state: TableState::default(),
            refresh_in_flight: false,
            rank_in_flight: true,
            rank_open: true,
            rank_class_idx: 0, // "impl"
            rank_output: None,
        };

        // Out-of-order stale completion for "review"
        let stale_msg = Message::RankDone {
            class: "review",
            result: Ok("output for review".to_string()),
        };

        if let Message::RankDone { class, result } = stale_msg {
            if class == RANK_CLASSES[model.rank_class_idx] {
                model.rank_in_flight = false;
                model.rank_output = Some(result.unwrap());
            }
        }

        // Must still be in flight and no output
        assert!(model.rank_in_flight);
        assert!(model.rank_output.is_none());

        // Correct completion for "impl"
        let valid_msg = Message::RankDone {
            class: "impl",
            result: Ok("output for impl".to_string()),
        };

        if let Message::RankDone { class, result } = valid_msg {
            if class == RANK_CLASSES[model.rank_class_idx] {
                model.rank_in_flight = false;
                model.rank_output = Some(result.unwrap());
            }
        }

        assert!(!model.rank_in_flight);
        assert_eq!(model.rank_output.as_deref(), Some("output for impl"));
    }
}
