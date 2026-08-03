---
name: consult
description: Use when a task warrants an outside model — a second opinion, an independent review, a cross-check from a different model family, or handing a well-scoped lane of work to another agent CLI (Codex, Antigravity, Kiro, headless Claude). Not for trivial single-file work that is faster done inline.
---

# Consult — delegate to an external agent CLI

Consult routes a task to the right model through the right harness, invokes it
headlessly, and treats its output as evidence to verify — not proof.

## When NOT to consult
Delegation has real overhead: the child loads its own context, may sit in
retry backoff, and its work must be verified. If the task is a single-file
change, a quick lookup, or anything you can finish inline faster than you can
brief a delegate — do it yourself. Consult when model diversity, independent
judgment, or parallel capacity materially improves the result.

## Resolve: which model, which harness
1. Classify the task into a tier via references/routing.md "Task tiers".
2. Walk that tier's ranked list in "Preferences"; drop anything in
   "Exclusions".
3. Run scripts/probe.sh — which CLIs are installed, what they serve.
4. First surviving model wins. If more than one installed harness serves it,
   apply "Harness selection" (native pairing; Kiro = flexible/open-weight
   lane).
5. Load references/<harness>.md for the recipe. Record one line:
   `consult: <tier> → <model> via <harness> (<reason>)`.

## Invoke: non-negotiable rules
- Headless/exec mode only; interactive modes hang in this environment.
- Read-only sandbox by default. Write access only when the user's request
  authorized implementation — and then inside an isolated git worktree.
- Multi-line prompts via a temp file (`"$(cat file)"`) or stdin — never long
  inline shell args.
- Close stdin (`</dev/null`) and set a hard `timeout`.
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
- Auth, quota, network, timeout, and task failures are NOT drift — report
  them as what they are; do not rediscover.

## After: verify
The child's claims are evidence. Check the diff, read the files it says it
changed, run the verification you would run for your own work. Report
outcomes faithfully, including partial or failed delegations.
