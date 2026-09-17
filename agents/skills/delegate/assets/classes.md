# Class guide

Choose one Class from the result the Brief asks for and the judgment needed to
produce it. Use the examples and boundaries below when two Classes seem to fit.

## scout

Find and explain facts about the software. The Brief asks for locations, source
reading, or a bounded search, and the deliverable is a report with evidence.

- Locate the config reader and quote the call sites.
- Summarize how a dependency is used, with file paths.
- List the existing tests that cover one function.

A request to find a file and edit it, or find a bug and fix it, belongs in impl
or hard-impl. A transformation with a specified mapping belongs in mechanical.

Conflicting sources, an unclear search boundary, or deciding which pages matter
can justify a higher Tier.

## mechanical

Apply a specified transformation. The Brief supplies the mapping and output
shape, leaving little semantic choice.

- Rename a symbol across files under a given mapping.
- Extract fields from logs into a specified schema.
- Strip a deprecated flag from every call site that already matches a pattern.

Use impl if the worker must choose an API, design the mapping, or decide how to
change the code to meet the required behavior. Use scout for locating or
summarizing information.

A fixed transformation may need a higher Tier when generated code, overlapping
names, or encoding make its edge cases difficult.

## impl

Turn a supplied specification into code changes with executable checks. The
Brief names the target behavior, files to change, and evidence needed to accept
the result. Product decisions are settled before dispatch.

- Add a documented command and its tests.
- Implement an agreed parser against fixtures already in the tree.
- Wire an existing helper through a specified call path.

Use scout for an explanation and mechanical for a rename with a complete mapping.
An existing patch that needs assessment belongs in review. Unresolved technical
problems may require hard-impl; a missing specification may need more planning
in this session before the work can be delegated.

Consider a higher Tier when a change crosses many files, depends on subtle
invariants, or could introduce errors that the tests would miss. The size of a
specified change alone does not make it hard-impl.

## review

Independently assess a diff against its requirements and evidence. Name the
author in the Brief and use a reviewer from a different Model family. The
reviewer returns findings.

- Check a parser patch for regressions against the spec.
- Inspect an access-control diff for missed paths.
- Verify that a claimed test covers the failure it names.

Writing the patch or applying fixes belongs in impl. Use scout for an
investigation without a diff to assess.

Adversarial inputs, concealed failure modes, or claims that depend on subtle
invariants may need a higher Tier.

## hard-impl

Implement a bounded task whose technical difficulty remains unresolved. The
root cause may be ambiguous, architecture constraints may compete, or a simpler
approach may already have failed. The deliverable is a patch with checks.

- Repair a concurrency defect with a stated invariant.
- Implement a cross-cutting storage migration under given constraints.
- Replace a failed approach with a specified alternative after the first impl missed.

Use impl when the specification is enough to guide an ordinary implementation.
Long, repetitive edits belong in mechanical; reconnaissance without a patch
belongs in scout. Keep unbounded strategy in this session until it can become
a concrete Brief.
