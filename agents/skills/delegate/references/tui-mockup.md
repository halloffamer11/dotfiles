delegate-mon  v0  |  cache 11m  |  2026-09-02 23:00  |  JSONL ~/.cache/delegate/ledger.jsonl
┌─ meters ──────────────────────────────────────────────────────────────┬─ open threads ─────────────────────┐
│ agy-gemini     5h ████████████████░░░░  87%  wk █████████████████░  90% │ lane            class   elapsed st │
│                bind 5h     reset 00:40   pace 2.58  ahead              │ flash-high@agy  scout     0:42  run │
│ agy-claude-gpt 5h ████████████████░░░░  80%  wk ███████░░░░░░░░░░░  36% │ luna@codex      mech      2:11  run │
│                bind weekly reset Sep 5   pace 0.89  behind             │                                       │
│ grok           5h —                     wk ██████████████░░░░░░  72% │ (finish events from dispatch.sh;     │
│                bind weekly reset Sep 8   pace 0.84  behind             │  unmatched start => running)          │
│ claude-general 5h ████░░░░░░░░░░░░░░░░  19%  wk ██████████░░░░░░░░  49% │                                       │
│                bind 5h     reset 01:19   pace 0.61  behind             │                                       │
│ claude-fable   5h ████░░░░░░░░░░░░░░░░  19%  wk █████░░░░░░░░░░░░░  27% │                                       │
│                bind 5h     reset 01:19   pace 0.33  behind             │                                       │
│ codex          5h ████████░░░░░░░░░░░░  39%  wk ███░░░░░░░░░░░░░░░  15% │                                       │
│                bind weekly reset Sep 7   pace 0.24  behind             │                                       │
└───────────────────────────────────────────────────────────────────────┴───────────────────────────────────────┘
┌─ burn  remaining weekly %   [1h]  24h  7d ───────────────────────────────────────────────────────────────────┐
│ 100┤                                                                                                          │
│    │  gemini · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·                      │
│  70┤                                         grok · · · · · · · · · · · · · ·                                 │
│    │                    claude-gpt \                                                                          │
│  40┤                                      \____                                                               │
│    │  claude-general ~~~~~~~~~~~~~~~~~~~~~~~~~~\____                                                          │
│  10┤  GATE · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·   codex ___                    │
│   0└────── 22:00 ────────────── 22:20 ────────────── 22:40 ────────────── 23:00 ─────────────────────────────┘
│  legend  agy-gemini  agy-claude-gpt  grok  claude-general  claude-fable  codex                                 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
  r refresh (in flight: no)   k rank overlay   1/2/3 burn window   j/k threads   q quit
  thresholds  remaining: green ≥40%  yellow 10–40%  red <10% (GATE)     pace: green >1.0 ahead, else behind

# empty threads (same meters, no unmatched dispatch.start)
┌─ open threads ─────────────────────┐
│ lane            class   elapsed st │
│ — none —                           │
│ dispatch.sh does not yet emit      │
│ start/finish; this panel stays     │
│ empty until the event contract     │
│ lands.                             │
└────────────────────────────────────┘

# rank overlay (key k) — read-only, last class or prompt
┌─ rank scout ─────────────────────────────────────────────┐
│ 1. flash-high@agy    pace 2.58  weekly 90%  r 87%  ok    │
│ 2. flash-medium@agy  pace 2.58  weekly 90%  r 87%  ok    │
│ 3. luna@codex        pace 0.21  weekly 13%  r 13%  ok    │
│                                                          │
│ (display only. TUI does not dispatch.)                   │
└──────────────────────────────────────────────────────────┘
