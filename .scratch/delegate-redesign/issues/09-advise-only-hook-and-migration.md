# 09 — Advise-only hook and migration

**What to build:** The last of the old routing is removed and the guardrails become advice. The gate hook keeps adding context (meter table and a pointer to `/delegate`) and loses every deny and ask rule, every environment-variable switch, and every threshold read. The global CLAUDE.md Delegation section becomes one line naming `/delegate`. The static lane table, the shell dispatcher, and the old routing reference are deleted or rewritten to the new design. The courier agent is rewritten as an optional background-and-poll wrapper for Workflow callers, with its turn limit raised, and is referenced by nothing on the main path. The skill's context file describes the finished layout.

Orin runs the spec acceptance list as the final assessment before this ticket closes.

**Blocked by:** 04 The `/delegate` skill; 05 Typed-only harness wrappers.

**Status:** landed 2026-09-09 (commits 7c76843, 9545e6f; tag delegate-v1-last); unticked items wait on Orin: the one-line Delegation section in ~/.claude/CLAUDE.md and the DELEGATE_BALANCE export in ~/.zshrc.local (both blocked for the session), and the §9 walk

- [x] Spawning a Claude worker without a reason is no longer denied; the hook only adds context
- [ ] No environment-variable switch remains anywhere in the skill, hooks, or docs; `mode` and `balance` do not exist as settings
- [ ] Every file the hook, the skill, and the context files name exists (re-opened 2026-09-09: three dead references found — see ticket 10)
- [x] The old lane table and shell dispatcher are gone and nothing references them
- [ ] The global CLAUDE.md Delegation section is one line
- [x] Existing tests and the TUI build pass after the deletions
- [ ] Orin walks the eight acceptance items in spec section 9 and signs each off

## §9 walk, 2026-09-09

| # | Item | State |
|---|---|---|
| 1 | Grok timeout, partial kept | **Signed off.** Spec amended: the item asked for status `timeout`, which contradicts §6.5 mapping timeout to `blocked`. Evidence is `tests/test_dispatch.py`, which proves the partial `final.txt` survives; no live grok run has ever timed out |
| 2 | No tool-call bound | **Open, decided.** The harness cap is gone but `preamble.md` asks every worker to stop after 40 tool calls. Leash kept for `scout` and `mechanical`, dropped for `impl` and `hard-impl`, plus a per-dispatch override. Ticket 11 |
| 3 | agy empty → `blocked` with a reason | **Signed off.** `tests/test_dispatch.py` cases 2c and 5 |
| 4 | Run directories outlive the session | **Signed off.** 14 directories under `~/.cache/delegate/runs/`, spanning three sessions |
| 5 | Brief reaches the CLI byte for byte | **Signed off.** Verified on run `20260909T181534Z`: a 9,762-byte brief sits verbatim inside the 12,049-byte prompt the relay reads |
| 6 | Every named file exists | **Open.** Re-opened after three dead references were found; ticket 10 |
| 7 | No env var switch | **Open.** `export DELEGATE_BALANCE=1` at `~/.zshrc.local:1`; nothing live reads it |
| 8 | Claude lane read-only smoke run | **Signed off.** Two `fable-xhigh@claude` runs, `sandbox: null`, `status: completed` |

Five of eight signed off. The checkbox above closes when 2, 6 and 7 do.
