# Delegate modular work

The coding-only implementation landed at `561aca4` (2026-09-16), with
final display/documentation corrections at `9dc7b66` and the accepted guide
redraft at `a24d20e`. Tickets 01–13
carry Landed notes and verification. Orin accepted ticket 10’s examples and
requested a humanizer redraft, now applied.

All 13 delegate script suites pass, plus full and focused PTY checks. Independent
Meter/catalog review found two cache validity gaps, fixed at `9a74a4f`. Separate
model-inspection and focused-setup/metering reviews found no actionable regression.
Worker runs are adjudicated in the delegate ledger. No worker remains active;
completed worktrees are removed. Read the numbered tickets for scope and decisions.

Before relying on research claims, read
[verification notes](research/2026-09-15-verification-notes.md). They qualify the
multi-domain scope and the agy quota-axi comparison.

Orin accepted agy unknown combined Remaining/Pace and authorized cutting the
coding-only ticket set. The decision and session evidence are in
[13](issues/13-agy-unknown-bound.md). C1–C8 and M1–M5 overlap: 04/05/09 together
cover M1, and 08 covers both C8 and M4. M2 and M3 bring C9–C12 into this cut.

Per-domain schema, new Classes, live conversion and automation enablement
(M6–M11) remain proposals. The consultation's native handoff, return contract,
ledger, test-surface and browser-probe work (C14–C18) remains deferred research;
include browser_probes.py in any later Domain consumer audit.

Orin approved a non-Claude worker for this batch's TUI changes on 2026-09-16,
because this session cannot spawn the native Opus lane. Preserve the existing
TUI design and verify state transitions.

`research/prompt.md` is this effort's original research brief, kept as scope history.
