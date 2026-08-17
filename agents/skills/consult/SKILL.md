---
name: consult
description: Route work to the right model through the right harness — a second opinion, an independent review, a cross-check from a different model family, or a well-scoped lane of work handed to another agent CLI (Codex, Antigravity, Kiro, headless Claude). Also use when CONSULT_BALANCE=1 and the primary harness's subscription window is running low: self-contained routine or mechanical work that would normally be done inline (or by an internal subagent) should be pushed to an external harness with quota to spare. Also use to answer questions about remaining subscription usage or reset times, or which models each installed agent CLI serves (scripts/usage.py, scripts/probe.sh). Not for trivial single-file work that is faster done inline when quota is not a concern.
---

# Consult — route work to the right model, harness, and quota

Consult picks a model for the task, picks the harness that serves it, checks
whether that lane still has subscription headroom, invokes it headlessly, and
treats the child's output as evidence to verify — not proof.

Two reasons to consult:
1. **Capability** — a different model family, an independent reviewer, or a
   harness that is simply better at the lane (Codex for GPT, Antigravity for
   Gemini). This is the default reason and works everywhere.
2. **Quota balancing** — only when `CONSULT_BALANCE=1` (personal machines;
   set in `~/.zshrc.local`, never stowed). Several subscriptions burn down
   at very different rates; the goal is that they run out *together*, not
   that Claude hits its wall while Antigravity sits at 99%. Balancing is
   total: it governs external harness choice AND which Claude model an
   internal subagent gets AND whether subagent-shaped work goes to the
   Agent tool or out to consult.

## When NOT to consult
Delegation has real overhead: the child loads its own context, may sit in
retry backoff, and its work must be verified. With balancing off, if the
task is a single-file change, a quick lookup, or anything you can finish
inline faster than you can brief a delegate — do it yourself. With balancing
on, the bar drops for *self-contained* routine/mechanical work when the
primary lane is low; it never drops for work that needs your live context.

## Resolve: which model, which harness, which lane
1. Classify the task into a tier via references/routing.md "Task tiers".
2. Walk that tier's ranked list in "Preferences"; drop anything in
   "Exclusions".
3. Run scripts/probe.sh — which CLIs are installed, what they serve, and
   (when `CONSULT_BALANCE=1`) the `## usage` block: one line per lane with
   effective remaining `r`, binding window, reset time, and status.
   (probe shows no catalog for claude: aliases/IDs live in
   references/claude.md → Models.)
4. Choose:
   - **Optimal** (`CONSULT_BALANCE` unset/0): first surviving model wins.
   - **Balanced** (`CONSULT_BALANCE=1`): apply routing.md "Balancing
     policy" — lanes with `status: unavailable` are skipped; among the
     eligible ranks (top rank, or one rank down — never Exclusions, and
     deep-reasoning always takes rank 1) pick the highest `r`; within 15
     points, quality rank wins. If no frontier lane is available for a
     hard-coding/deep-reasoning task, stop and report the earliest reset.
     If a lane is unavailable but `rollover_soon` is true, surface the reset
     time and ask the user whether waiting beats degrading.
5. If more than one installed harness serves the model, apply "Harness
   selection" (native pairing; Kiro = flexible/open-weight lane).
6. Load references/<harness>.md for the recipe. Record one line:
   `consult: <tier> → <model> via <harness> (<reason>[; balanced: r=NN%, skipped X (why)])`.

## Invoke: non-negotiable rules
- Headless/exec mode only by default; interactive modes hang in this
  environment. Exception — herdr visibility: when the user asks to watch
  ("in herdr", "where I can see it") and `HERDR_ENV=1`, run the child in a
  new `--no-focus` herdr tab labelled after the task (references/herdr.md)
  and leave the tab open for the user; never auto-select herdr.
- Read-only sandbox by default. Write access only when the user's request
  authorized implementation — and then inside an isolated git worktree.
- Multi-line prompts via a temp file (`"$(cat file)"`) — never long inline
  shell args.
- Close stdin (`</dev/null`) and enforce a hard timeout. macOS ships no `timeout`
  binary: use your harness's command-timeout mechanism (e.g. the Bash tool's
  timeout parameter), or `gtimeout` if coreutils is installed.
- Every brief states: objective, working directory, in-scope files,
  constraints, definition of done, expected return format — and tells the
  child: do not delegate further; no external side effects.
- Never use permission-bypass or full-access flags.

## Staleness protocol (version-gated recipes)
- Before invoking: `command -v <cli>` and `<cli> --version` (near-free). If
  the version matches the recipe's `verified-against` stamp, invoke
  immediately.
- On version mismatch, unknown-flag, or usage error: run that subcommand's
  `--help` (and the model-list command if it is a model error), adapt, retry
  ONCE, then report the drift to the user so they can update the reference
  file. Never edit the reference files yourself.
- Auth, network, timeout, and task failures are NOT drift — report them as
  what they are; do not rediscover. A **quota** failure is also not drift:
  run `scripts/usage.py --refresh`, mark the lane unavailable, and re-resolve
  once.

## After: verify
The child's claims are evidence. Check the diff, read the files it says it
changed, run the verification you would run for your own work. Report
outcomes faithfully, including partial or failed delegations.
