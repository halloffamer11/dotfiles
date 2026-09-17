# Class guide

Judgment for the five Classes. Names, Floor and Ceiling live in `routing.json`. Rank prints the live Range on its header (`floor=` `ceiling=`). This file does not set those numbers.

Pick exactly one Class. When two seem to fit, the counter-examples decide. Named dispatch (`dispatch --lane`) skips the Class Range; still write the Class on the prompt, because the leash reads it.

When `rank.py` or `delegate.py run` prints `STOP: no lane eligible for <class>` and exits 1, start no worker. Show the veto lines. Ask the user which to do:

- abort
- named dispatch to a lane they name
- a one-job exception they state in prose

`--tier` cannot admit a Range whose every tier is gated. The script does not prompt.

## scout

### Intent

Find, ground, and summarize facts about the software. No patch.

### Signals

The brief asks for locations, a source reading, or bounded reconnaissance. Acceptance is a report, not a diff.

### Examples

- Locate the config reader and quote the call sites.
- Summarize how a dependency is used, with file paths.
- List the existing tests that cover one function.

### Counter-examples

- "Find the file, then edit it" is impl.
- "Find the bug and fix it" is impl.

### Default tier

The Floor in `routing.json`. Read `floor=` and `ceiling=` from the rank header.

### When to raise

Raise `--tier N` inside the printed Range when sources conflict, the search boundary is ambiguous, or the scout must judge which of the given pages matter.

### When not to use this class

Use impl or hard-impl when the deliverable is a patch. Use mechanical when the mapping is already specified and the work is a transform.

## mechanical

### Intent

Apply a specified transformation: renames, mechanical edits, extraction into a fixed shape.

### Signals

The brief gives an explicit mapping and a fixed output shape. Little semantic choice remains.

### Examples

- Rename a symbol across files under a given mapping.
- Extract fields from logs into a specified schema.
- Strip a deprecated flag from every call site that already matches a pattern.

### Counter-examples

- Choosing a new API is impl.
- Inventing the mapping as you go is impl.

### Default tier

The Floor in `routing.json`. Read `floor=` and `ceiling=` from the rank header.

### When to raise

Raise `--tier N` inside the printed Range when the transform is fixed but the edge cases are tricky (generated code, overlapping names, encoding). Reclassify if the transform itself still needs design.

### When not to use this class

Use impl when behavior is specified but the shape of the change is not. Use scout when the job only locates or summarizes.

## impl

### Intent

Implement a supplied specification as code changes with executable acceptance.

### Signals

The brief names target behavior, the files to change, and checks that prove the change. A spec exists; the worker does not invent the product.

### Examples

- Add a documented command and its tests.
- Implement an agreed parser against fixtures already in the tree.
- Wire an existing helper through a specified call path.

### Counter-examples

- Read-only explanation is scout.
- A rename with a complete mapping is mechanical.
- Missing-spec architectural uncertainty is hard-impl, or more planning in this session, not a guess.

### Default tier

The Floor in `routing.json`. Read `floor=` and `ceiling=` from the rank header.

### When to raise

Raise `--tier N` inside the printed Range when the change crosses many files, the invariants are subtle, or a wrong edit is hard to see in the tests.

### When not to use this class

Use scout when there is no patch. Use review when the patch already exists and must be judged. Use hard-impl when the difficulty is the unresolved technical problem, not the size of a specified change.

## review

### Intent

Independently assess a diff. The reviewer family differs from the author.

### Signals

The brief names the author, the diff, the requirements, and the evidence to check. Acceptance is findings, not a repaired tree.

### Examples

- Check a parser patch for regressions against the spec.
- Inspect an access-control diff for missed paths.
- Verify that a claimed test covers the failure it names.

### Counter-examples

- Editing the fixes is impl.
- Writing the patch under review is impl, on a different family than the reviewer.

### Default tier

The Floor in `routing.json`. Read `floor=` and `ceiling=` from the rank header.

### When to raise

Raise `--tier N` inside the printed Range when the input is adversarial, failure modes hide in the diff, or the claim depends on a subtle invariant.

### When not to use this class

Use impl when the job is to apply the fixes. Use scout when there is no diff yet.

## hard-impl

### Intent

Implement a bounded task with unresolved technical difficulty: an ambiguous root cause, competing architecture constraints, or a simpler approach that already failed.

### Signals

The brief has an ambiguous root cause, architecture constraints, or a simpler approach that already failed. The deliverable is still a patch with checks.

### Examples

- Repair a concurrency defect with a stated invariant.
- Implement a cross-cutting storage migration under given constraints.
- Replace a failed approach with a specified alternative after the first impl missed.

### Counter-examples

- Long repetitive edits are mechanical.
- A specified feature with a clear shape is impl.
- Unbounded strategy belongs in this session until it is briefable.

### Default tier

The Floor in `routing.json`. Read `floor=` and `ceiling=` from the rank header.

### When to raise

Raise `--tier N` only while the rank header still shows a higher Ceiling than the Floor. When the printed Range is already a single tier, keep this Class or reclassify; do not invent a number.

### When not to use this class

Use impl when the spec is enough and the difficulty is ordinary. Use mechanical for volume without design. Use scout for reconnaissance with no patch.
