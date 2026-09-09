# 09 — Advise-only hook and migration

**What to build:** The last of the old routing is removed and the guardrails become advice. The gate hook keeps adding context (meter table and a pointer to `/delegate`) and loses every deny and ask rule, every environment-variable switch, and every threshold read. The global CLAUDE.md Delegation section becomes one line naming `/delegate`. The static lane table, the shell dispatcher, and the old routing reference are deleted or rewritten to the new design. The courier agent is rewritten as an optional background-and-poll wrapper for Workflow callers, with its turn limit raised, and is referenced by nothing on the main path. The skill's context file describes the finished layout.

Orin runs the spec acceptance list as the final assessment before this ticket closes.

**Blocked by:** 04 The `/delegate` skill; 05 Typed-only harness wrappers.

**Status:** ready-for-agent

- [ ] Spawning a Claude worker without a reason is no longer denied; the hook only adds context
- [ ] No environment-variable switch remains anywhere in the skill, hooks, or docs; `mode` and `balance` do not exist as settings
- [ ] Every file the hook, the skill, and the context files name exists
- [ ] The old lane table and shell dispatcher are gone and nothing references them
- [ ] The global CLAUDE.md Delegation section is one line
- [ ] Existing tests and the TUI build pass after the deletions
- [ ] Orin walks the eight acceptance items in spec section 9 and signs each off
