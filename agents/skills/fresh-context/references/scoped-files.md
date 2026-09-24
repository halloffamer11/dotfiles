# Nested files and path-scoped rules

Sources: <https://code.claude.com/docs/en/memory> (rules, imports, AGENTS.md)
and <https://agents.md/> (nearest file wins).

## Nested CLAUDE.md with an AGENTS.md link

Use it for an instruction that applies in one directory. Codex and other
agents read the nearest `AGENTS.md`; Claude loads a subdirectory's
`CLAUDE.md` when it reads a file in that directory. So every harness gets it,
and none loads it until work reaches that directory.

```
cd <dir> && ln -s CLAUDE.md AGENTS.md
```

The link must point to the `CLAUDE.md` in the same directory. A link to an
ancestor's file loads the same text twice. Keep the nested file to what
applies in that directory only; it does not repeat the root file.

## Path-scoped rule

Use it when the files an instruction covers sit in many directories (a file
type, a naming pattern), which a nested file cannot express. One topic per
file, with a descriptive name: `.claude/rules/testing.md`, not `misc.md`.

```
---
paths:
  - "tests/**/*.py"
  - "src/**/*_test.py"
---
# Test conventions
- Use the fixtures in `tests/conftest.py`; do not build clients by hand.
```

`paths` is the only frontmatter field Claude Code reads. If the YAML does not
parse, the rule loads as if it had no `paths`.

## What each one costs

| Form | Loads |
|---|---|
| Root `CLAUDE.md` | Every session, at launch; re-read after `/compact` |
| `@path` import | At launch, with the file that imports it: it saves no context |
| Rule without `paths:` | Every session, at launch, like CLAUDE.md: it saves no context |
| Rule with `paths:` | When Claude reads a matching file |
| Nested `CLAUDE.md` | When Claude reads a file in that directory |

Workers in other harnesses never read `.claude/rules/`. When you delegate a
task that a rule covers, put the rule in the brief.
