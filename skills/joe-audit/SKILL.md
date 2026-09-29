---
name: joe-audit
description: >-
  Whole-repo audit for over-engineering. Scans the entire codebase, not a
  diff: a ranked list of what to delete, simplify, or replace with
  stdlib/native equivalents. Use when the user says "audit this codebase",
  "audit for over-engineering", "what can I delete from this repo", "find
  bloat", or "joe-audit". One-shot report, does not apply fixes.
---

lazyJoe, repo-wide. Scan the whole tree instead of a diff. Rank findings
biggest cut first.

Check for `CONVENTIONS.md` and `REVIEW.md`; apply every convention they define.

## Tags

Same as lazyJoe:

- `yeet:` dead code, unused flexibility, speculative feature. Replacement: nothing.
- `duh:` hand-rolled thing the standard library ships. Name the function.
- `NPC:` dependency or code doing what the platform already does. Name the feature.
- `cringe:` abstraction with one implementation, config nobody sets, layer with one caller.
- `glow up:` same logic, fewer lines. Show the shorter form.

## Hunt

Deps the stdlib or platform already ships, single-implementation interfaces,
factories with one product, wrappers that only delegate, files exporting one
thing, dead flags and config, hand-rolled stdlib.

## Output

One line per finding, ranked: `<tag> bloat <what to cut>. <replacement>. [path:L<line>]`.
End with `W: -<N> lines, -<M> deps.` Nothing to cut: `No notes. Ship it.`
Feed the list back as `bloat` rows of the [contract](CONTRACT.md) ledger, so the crew
cuts it without re-deriving the audit.

## Boundaries

Scope: over-engineering and complexity only. Correctness bugs, security holes,
and performance are out of scope; route them to `inspectorJoe` and `secretJoe`.
Repo-wide by design: list findings instead of deferring them to issues, because
the list is the deliverable. Lists findings, applies nothing. One-shot.
