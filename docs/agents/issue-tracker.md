# Issue tracker: Local Markdown

Tickets for this repo are markdown files under `.scratch/`. Specs are under
`docs/superpowers/specs/`. The GitHub repo is public and has no issues: do not
create issues there.

## Conventions

- One effort per directory: `.scratch/<effort-slug>/`.
- The spec is `docs/superpowers/specs/<YYYY-MM-DD>-<effort-slug>.md`, not a file
  under `.scratch/`.
- One file per ticket: `.scratch/<effort-slug>/issues/<NN>-<slug>.md`, numbered
  from `01`. Never one combined tickets file. A ticket inserted after another
  takes a letter suffix (`07b`).
- Near the top, a `**Blocked by:**` line names each blocker by number and title
  (`01 Lane catalog and validators; 03 One run through an ADS relay`), or says
  `None — can start immediately.`
- Acceptance criteria are `- [ ]` boxes, with a bold `**Status:**` line just
  above them. While a ticket waits, the Status value is a triage role from
  `triage-labels.md`. When the work lands, replace it with prose:
  `landed <date> (<commits>)`, `implemented <date>`, or `closed <date>`, and say
  which boxes are still open and whose they are.
- History goes at the bottom as dated `## ` sections. The last one is
  `## Landed, <date>`: what shipped, the commits, and how it was verified. There
  is no `## Comments` section.
- Evidence for an effort: `.scratch/<effort-slug>/_data/` for accepted data,
  `.scratch/<effort-slug>/research/` for research notes.

## When a skill says "publish to the issue tracker"

Create the next-numbered file in `.scratch/<effort-slug>/issues/` (make the
directory if it does not exist), with a `**Blocked by:**` line, the boxes, and
`**Status:** needs-triage`, or the role the skill names.

## When a skill says "fetch the relevant ticket"

Read the file at the path given. A bare number `NN` means
`.scratch/<effort-slug>/issues/NN-*.md`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`,
  with the question in the body. A `**Type:**` line records the ticket type
  (`research`/`prototype`/`grilling`/`task`); the `**Status:**` line records
  `claimed`/`resolved`.
- **Blocking**: the `**Blocked by:**` line near the top. A ticket is unblocked
  when every ticket it lists is `resolved`, `landed` or `closed`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open,
  unblocked, and unclaimed; first by number wins.
- **Claim**: set `**Status:** claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set
  `**Status:** resolved`, then append a context pointer (gist + link) to the
  map's Decisions-so-far in `map.md`.
