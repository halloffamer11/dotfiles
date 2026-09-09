# 05 — Typed-only harness wrappers

**What to build:** Four sibling skills, `/delegate-claude`, `/delegate-codex`, `/delegate-agy`, `/delegate-grok`, that only a human can invoke. Each takes a lane name or a model, resolves it against the catalog, and calls dispatch. They read no meter and apply no ranking. About twenty lines each; shared logic lives in dispatch, not in the wrappers.

**Blocked by:** 03 One run through an ADS relay.

**Status:** landed 2026-09-09 (commit 7c76843); wrappers stowed by `make skills`

- [x] Each wrapper has model invocation disabled in its frontmatter and does not appear in the model's skill list
- [x] `/delegate-codex --lane terra-high@codex <brief>` runs the named lane without a meter probe
- [x] `/delegate-grok --model grok-4.6 <brief>` resolves the model to its lane; an unknown model fails with a message listing the lanes on that harness
- [x] A wrapper for a harness whose CLI is absent fails before dispatch with a plain message
- [x] One typed smoke run on each wrapper leaves a run directory (code path smoked 2026-09-09 on all four harnesses; run dirs 20260909T1800*)
