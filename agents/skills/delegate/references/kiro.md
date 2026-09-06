# Kiro CLI (kiro-cli, AWS) — invocation reference

verified-against: none on this machine — kiro-cli is not installed on the Linux host (2026-09-06). Flags were cross-checked against the public command reference (kiro.dev/docs/reference/cli-commands, read 2026-09-06): `--no-interactive`, `--trust-tools`, `--trust-all-tools`, `--agent`, `--effort low|medium|high|xhigh|max`, `--resume-id` and `--list-models` are documented there; `--model` is NOT, and everything said about it below is carried over from work-machine notes (kiro-cli 2.19.x and 2.20.2, 2026-08-20..31). Run `kiro-cli --version` and `kiro-cli chat --help` before first use and replace this stamp.

## Read-only
kiro-cli chat --no-interactive --trust-tools=fs_read \
  --model <slug> --effort <low|medium|high|xhigh|max> \
  "$(cat <promptfile>)" </dev/null

- `--no-interactive` runs one turn, prints the answer to stdout, exits.
- `--trust-tools=<comma-list>` is the sandbox: `fs_read` alone is the
  read-only research lane. An empty `--trust-tools=` was observed to grant
  no tools at all (not in the reference; confirm on `--help`).
- The invocation cwd is the workspace the child sees — launch from the
  directory it should be grounded in.
- `--resume-id <SESSION_ID>` continues an earlier child from the same cwd.

## Write-enabled (only when the user authorized implementation; isolated worktree)
Same but `--trust-all-tools` (full trust, shell included) with cwd set to
the worktree. Tool trust is the only guard the flag gives you; the
worktree is the boundary.

## Models
`kiro-cli chat --list-models` is the catalog (probe.sh runs exactly this).
`--format json` (`plain|json|json-pretty`) is documented only on doctor,
settings, whoami and diagnostic; it was observed on `chat` — confirm on `--help`.
The catalog is multi-vendor — OpenAI, Anthropic and open-weight slugs —
and prints each slug's credit multiplier and context size: read both from
the live catalog, never from a copy in this file. `auto` (the default)
lets Kiro route.

## Agent profiles (`--agent <name>`)
`kiro-cli agent list`. Workspace `.kiro/agents/<name>.json` overrides
global `~/.kiro/agents/<name>.json`. A profile's `model` field pins the
model and its tools list scopes the tools; a profile grants no trust by
itself, so still pass `--trust-tools` per invocation. Compose a new thin
profile rather than editing one you do not own, and smoke-test it
headless before labelling a lane with it.

## Not a lane (yet)
kiro has no rows in lanes.json, no case in scripts/dispatch.sh (`unknown
harness`) and no meter in scripts/usage.py. Until those exist
(routing.md §6) this is a hand-run recipe: call it inline, write the
delegate record line yourself, and route by routing.md — this file
carries no routing rules. evals/browser/run.sh's `run_kiro` is a stub.

## Quirks
- Version gate on headless `--model`. On <= 2.19.x, `--no-interactive
  --model <m>` warns `failed to set model '<m>': Method not found` and
  then SILENTLY answers on the default profile's model (interactive
  `--model` worked). Observed fixed from 2.20.2 (public release
  2026-08-31): the child self-identifies as the requested model with no
  warning. Check `kiro-cli --version` first. On <= 2.19.x pin the model
  through a thin agent JSON (`{"name":"<x>","model":"<slug>"}` in
  `~/.kiro/agents/<x>.json`) and pass `--agent <x>`.
- A missing `--agent` name falls back SILENTLY: one stderr line — `no
  agent with name <x> found. Falling back to user specified default` —
  then a successful run on the default profile. A profile that exists on
  one host may be absent on another; seen once as a lane routed to a GPT
  seat answering as Claude Opus, breaking reviewer-family ≠ author-family.
  Guards: `kiro-cli agent list | grep <name>` on the invoking host, and
  when identity matters open the prompt with "One line: which model are
  you (vendor and family)?" and check that answer plus stderr line 1
  before trusting the output.
- `--model` is not in the public command reference — treat it as
  observed-not-documented until `kiro-cli chat --help` here lists it.
- Close stdin (`</dev/null`) as with every harness. Per-item lanes are one
  `--no-interactive` call each, wrapped in `timeout` (evals/browser/run.sh
  uses `gtimeout` where Homebrew provides it).
