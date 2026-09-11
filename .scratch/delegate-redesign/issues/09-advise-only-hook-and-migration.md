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

## §9 walk continued 2026-09-10

The three criteria left unsigned were walked again after the day's eight commits.
Every claim below was checked by hand, not taken from the walk's report.

**§9.2 — "No implementation run is bounded by a tool-call limit." Satisfied.**
`should_leash` in `scripts/delegate.py` returns False for `impl` and `hard-impl`,
`build_prompt` splices the sentence only when the leash is active, and
`assets/preamble.md` no longer carries it. `tests/test_dispatch.py` covers a
`hard-impl` prompt without it, a `scout` prompt with it, and `--no-leash`. Signed
off under the 2026-09-09 amendment; `review` keeps the leash as a reading job.

**§9.6 — "Every file the hook or docs name exists." Was open; two of three now
fixed.** Verified by listing the files:

- `references/CLAUDE.md` told every agent to read
  `~/.claude/skills/delegate/references/routing.md` before routing. That file was
  deleted in the redesign and the directory holds only `kiro.md`,
  `tui-mockup.md` and `tui-research.md`. Now points at `SKILL.md` and names
  `routing.json` as the rules. **Fixed.**
- `agents/skills/delegate/CLAUDE.md` still said "**agy is still broken**… an agy run
  that needs tools must be given `--write`". Ticket 14 closed on 2026-09-10 and
  `ADS_COMMIT` pins both read-only fixes, so that advice sent agents reaching for a
  much larger blast radius than they needed. **Fixed.**
- `~/.claude/hooks/delegate-gate.py:56` tells every session to run
  `{SKILL_DIR}/delegate.py`. That path does not exist — ticket 10 moved it to
  `scripts/delegate.py`, confirmed by `ls`. **Still open, and outside this repo**:
  the hook is a standalone file in Orin's harness, not stowed from here, so it is
  his to change. One word: `delegate.py` → `scripts/delegate.py`.

**§9.7 — "No env var switch remains." Needs a human, unchanged.** No repo code
reads `DELEGATE_BALANCE`; the dead `export DELEGATE_BALANCE=1` is still line 1 of
`~/.zshrc.local`, which only Orin should edit.

Also confirmed while walking: `commandcode-delegate` passes
`--permission-mode plan` but is unreachable — `commandcode` is not in
`catalog.HARNESSES`, has no lane and no wrapper. `claude-delegate` passes it too
and **works**, because Claude Code runs `Read`, `Glob` and `Grep` without prompting
under plan mode; run `20260909T180126Z-fable-xhigh@claude-ca924983` did exactly
that with `readOnlyViolation: false`. So ticket 14's second follow-up is a latent
inconsistency, not a live defect.
