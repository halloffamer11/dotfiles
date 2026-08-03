---
name: council
description: Convene a multi-model council — sealed memos from independent harnesses, adjudicated by the routing lead — for a critical decision. Explicitly invoked only.
disable-model-invocation: true
---

# Council — multi-model deliberation for critical decisions

Cost gate first: a council run costs roughly 3–10x a single-agent answer.
Convene one only when being wrong costs more than the tokens. State the
estimated cost before proceeding.

The defaults below are strong; deviate deliberately and say why.

## 1. Frame the brief
One brief, received identically by every panelist:
- The decision, in one sentence, and who owns it.
- Constraints, reversibility, deadline, success criteria.
- A sanitized evidence packet: relevant facts only; strip secrets and any
  hint of your own current lean.

## 2. Compose the panel
- Run ../consult/scripts/probe.sh for real availability.
- Panelists: available harnesses serving models from different families.
  Exclude your own model family — no agent grades its own work.
- Quorum (routing.md "Council defaults"): ≥2 families besides the lead's.
  Below quorum: report the real composition and STOP. Never simulate absent
  panelists — a role-played council is worse than no council.
- Deliberation shape is your judgment call: default is sealed memos only;
  add at most one challenge round, only when memos materially conflict.

## 3. Collect sealed memos
Invoke each panelist under the consult skill's rules (read-only, headless,
temp-file prompts, hard timeout). Same brief to all; no panelist sees
another's memo in the sealed round. Required memo schema:
recommendation · key assumptions · failure modes · confidence ·
what would change my mind.

## 4. Adjudicate
Adjudicator: the routing.md lead — highest-ranked available deep-reasoning
model (reached via consult if that is not you).
- Judge against the brief's success criteria, never by vote count.
- Name each real disagreement as a crux: what it turns on, what evidence
  would resolve it.
- Output: decision · strongest dissent (addressed, not smoothed) ·
  unresolved uncertainty · revisit trigger.
- If confidence is low, say plainly: "this decision is the user's, not the
  council's." Manufactured consensus is the cardinal failure.

## Record
End with one line: panel composition (model via harness, each), quorum
status (MET or DEGRADED), decision, where dissent remains.
