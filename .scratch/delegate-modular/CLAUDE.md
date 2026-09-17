# Delegate modular work

Research is merged at `6467747`. Implementation is in progress. Tickets 01–07, 09, 10 and 13 are integrated
through `49a628b`; independent review is running. Ticket 10’s examples await
Orin’s review. Ticket 11’s CLI landed at `43f3eb1`; its focused screens and ticket 08 are in
one active worker. Ticket 12 is in a separate worker. All 13 delegate script
suites passed on the integrated foundation and CLI.

For implementation or triage, read the numbered tickets in `issues/` and their
source notes. Each ticket names its blockers and acceptance checks. Start with
the first unlanded ticket whose blockers are satisfied. Tickets 08, 11 and 12
now have concrete CLI contracts. Active workers use isolated worktrees under
`/private/tmp/delegate-modular-20260916/`; inspect their state before restarting work.

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

Orin approved a non-Claude worker for the upcoming TUI changes on 2026-09-16,
because this session cannot spawn the native Opus lane. Preserve the existing
TUI design and verify state transitions.
