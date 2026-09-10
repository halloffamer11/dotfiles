# 14 — Read-only dispatch is unusable on grok and agy

**What to build:** A read-only dispatch to `grok` or `agy` dies at its first tool call. Both harnesses are effectively toolless in the mode delegate puts them in, and delegate routes work to them anyway. This is our defect, not the worker's.

**Evidence, 2026-09-09.** The same research brief went read-only to three lanes. `terra-high@codex` returned a full report in 6 minutes. The other two:

- `grok46-high@grok`, run `20260909T200714Z-grok46-high@grok-3e66a330`, 17s. Its `events.jsonl` ends: `tool_call run_terminal_command` → `status: failed`, content `"User cancelled the execution"` → `end`, `stopReason: "cancelled"`. Grok's first action was cancelled at the permission gate and the turn ended. The relay reported `completed`, so this surfaced as `partial` with "no return block in final message" — a true statement that hides the cause.
- `flash-high@agy`, run `20260909T200707Z-flash-high@agy-239ffb4d`, 39s, no `events.jsonl` at all. Reason: Antigravity auto-denied the `read_url` permission because headless `--print` cannot prompt.

**Root cause.** `delegate.py run_relay` passes `--read-only` for every harness. In the pinned ADS relays that flag means different things:

- codex, claude: a real read-only sandbox. Tools work. Unaffected.
- grok: `--sandbox read-only --permission-mode plan` (the relay's own header, line 25). Plan mode cancels `run_terminal_command`.
- agy: `--mode plan` (relay header, line 45). Plan mode auto-denies every permission request in a headless run.

For grok and agy, read-only means plan mode, and plan mode in a headless run has no path to approve a tool. The relays expose no middle setting: grok offers only `--read-only` or `--full-access` (`--sandbox off`), agy only `--read-only` or `--dangerously-skip-permissions`. Delegate cannot fix this by choosing better flags on the pinned commit.

Also worth recording: grok's advertised tool list in that run was `run_terminal_command, read_file, search_replace, list_dir, grep, kill_command_or_subagent, todo_write, get_command_or_subagent_output, spawn_subagent`. There is no web fetch or search tool. Grok reached for a terminal because that is the only way out to the network — so even with permissions fixed, a browse-the-web brief is a poor fit for that lane.

**What to do**, in the order that gets value soonest:

1. Make the failure legible now. `map_result` should recognise `stopReason: "cancelled"` with a cancelled tool call and return `blocked` with reason `permission gate cancelled the run`, not `partial`. A wrong status is worse than a failure, because it costs the lead a debugging session.
2. Stop routing tool-needing work into a mode that cannot run tools. Either read-only dispatch to grok and agy is refused with the reason, or those lanes are marked as having no working read-only mode and ranking skips them for read-only jobs.
3. Upstream the real fix. The agreed strategy with amElnagdy/delegate-skills is pin, wrap, and send PRs. The PR is a middle permission setting: read-only sandbox with tool approval auto-granted, which is what a non-interactive review lane actually needs.

**Blocked by:** nothing.

**Status:** open, raised by Orin 2026-09-09: "debug why they failed. this is a defect in the delegate skill itself."

- [ ] A cancelled-at-the-gate run returns `blocked` with a reason naming the permission gate, not `partial`
- [ ] A read-only dispatch to a lane with no working read-only mode is refused before the relay starts, with the reason
- [x] The relay's meaning of `--read-only` per harness is written down in the skill's own context file, since it differs and the difference is load-bearing (commit 31154e5)
- [x] An upstream issue or PR against amElnagdy/delegate-skills asks for a middle permission setting, linked from this ticket
- [ ] A regression test drives the cancelled-tool-call event shape through `map_result` from a fixture

## Grok is fixed at the source, 2026-09-09

Item 3 is done for grok, and it turned out to need no middle setting — the enforcement was already
there and plan mode was smothering it.

**PR:** [amElnagdy/delegate-skills#119](https://github.com/amElnagdy/delegate-skills/pull/119),
from our fork `halloffamer11/delegate-skills`, branch `fix/grok-read-only-plan-mode`, commit
`f14dc1e`. `ads.sh` is pinned to that commit until it merges; the pin carries a comment saying how
to unwind it.

**The fix:** `--sandbox read-only --always-approve`, replacing
`--sandbox read-only --permission-mode plan`. On grok **1.0.25** the read-only sandbox is
kernel-enforced (Seatbelt on macOS, Landlock on Linux): grok's `write` and `search_replace` tools
and shell redirects all fail with `EPERM`. Verified against a throwaway repo **outside the temp
dirs** — three write attempts, all denied, tree clean. The relay's own header claimed the sandbox
did not cover grok's edit tool; that was true on 0.2.101 and is false now, so the comment was
corrected too. This also makes grok match `codex-delegate`, which leans on its sandbox alone.

**Evidence the lane is open:** the review brief that died at 17s now returns in 267s, `status: done`,
29 tool calls, `stopReason=end_turn`, with `touchedFiles: []` and `readOnlyViolation: false`.

### Still open

- **agy is untouched.** `--mode plan` still auto-denies every permission headless. Unlike grok, agy
  exposes no sandbox flag to lean on instead, so this is a real fix rather than a flag swap, and
  `delegate.py` still papers over it by telling agy in the prompt that it has no terminal.
  **This matters more than it looks: `agy` is the only worker CLI installed on omarchy.**
- The three legibility items above — `blocked` instead of `partial` at the gate, refusing a
  read-only dispatch to a lane with no working read-only mode, and the `map_result` fixture test —
  are unaffected by the upstream fix and still want doing. They are what makes the *next* failure of
  this shape legible.
