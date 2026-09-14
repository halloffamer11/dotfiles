# Objective
Read-only Standards review of the project dashboard implementation. Run `git diff ea60b33...HEAD` and `git log ea60b33..HEAD --oneline` in this frozen review worktree; the latter is the complete implementation commit list. Read CLAUDE.md, references/CLAUDE.md, CONTEXT.md, agents/skills/delegate/CLAUDE.md, tools/delegate-dashboard/CLAUDE.md, Makefile and docs/agents/issue-tracker.md as the repository standards sources. Inspect the whole diff and surrounding code needed to evaluate it. Authors used Codex; this review must be independent. Do not delegate, write files, commit, change configuration, control Herdr panes, or probe vendors. Skip tooling-enforced style findings.

Apply this full smell baseline, always as labelled judgement calls and subordinate to documented repository standards:
- Mysterious Name: a function, variable, or type whose name does not reveal what it does or holds. Rename it; if no honest name comes, the design is murky.
- Duplicated Code: the same logic shape appears in more than one hunk or file. Extract the shared shape and call it from both.
- Feature Envy: a method reaches into another object's data more than its own. Move the method onto the data it envies.
- Data Clumps: the same fields or parameters keep travelling together. Bundle them into one type.
- Primitive Obsession: a primitive or string stands in for a domain concept deserving its own type. Give it a small type.
- Repeated Switches: the same switch or if-cascade on a type recurs. Use polymorphism or one shared map.
- Shotgun Surgery: one logical change forces scattered edits. Gather what changes together into one module.
- Divergent Change: one module is edited for unrelated reasons. Split by reason for change.
- Speculative Generality: abstractions, parameters, or hooks exist for needs the spec lacks. Inline until there is a real need.
- Message Chains: long navigation exposes structure callers should not depend on. Hide the walk behind one method.
- Middle Man: a class or function mostly delegates onward. Call the real target directly.
- Refused Bequest: a subclass ignores or overrides most of its inheritance. Use composition.
# Definition of done
Report per file/hunk: (a) documented-standard violations, citing the standard file and exact rule; (b) baseline smells, naming the possible smell and quoting the hunk. Separate hard violations from judgement calls. The repository overrides the smell baseline. Under 400 words. If no actionable findings, say so. Return findings and evidence only, with file and line references; no code edits. Use read-only Git inspection to confirm your worktree stays unchanged. Inspect unfamiliar CLI help first; never pass permission-bypass flags yourself.
