---
name: superJoe
description: Orchestration for joe's agent crew.
---

Superjoe = a crew. Use it as an **iterative loop**, not a one-shot dispatch. The main thread runs the loop; agents do one step each.

## The loop

Run in order. Restart at step 1 whenever a later step fails.

1. **Build** — `builderjoe` produces minimal, working code.
1. **Simplify** — `lazyjoe` flags over-engineering and bloat. Cut it, or route back to `builderjoe`.
1. **Document** — `docujoe` documents the public surface in present tense.
1. **Test** — `testjoe` covers every branch, 100%, no unreachable code.
1. **Review** — `inspectorjoe` lists issues with location + one-line reason. Fix each, then re-run.
1. **Harden** — `secretjoe` hunts vulnerabilities. Fix or route to `builderjoe`.

## Exit gates

Ship only when ALL pass:

- `inspectorjoe` reports zero issues
- `testjoe` reports 100% coverage
- `secretjoe` finds nothing exploitable

Any gate failing sends the work back to the step that owns it. Keep looping until all three are green.

## When to use

| Task                                             | Agent          |
| ------------------------------------------------ | -------------- |
| Write minimal, surgical code / edits             | `builderjoe`   |
| Trim bloat / guard over-engineering              | `lazyjoe`      |
| Concise, goal-oriented docs                      | `docujoe`      |
| Review for minimalism, architecture, performance | `inspectorjoe` |
| Uncover vulnerabilities / security research      | `secretjoe`    |
| Read docs / find & evaluate packages             | `researchjoe`  |
| Orchestrate the loop / high-level design         | Main thread    |

Rule: main thread loops; each agent does one step. Spawn `researchjoe` from any step when a dependency or fact needs checking — it never edits.
