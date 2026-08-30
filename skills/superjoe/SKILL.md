---
name: superJoe
description: Orchestration for joe's agent crew.
---

SuperJoe = a crew. Use it as an **iterative loop**, not a one-shot dispatch. The main thread runs the loop; agents do one step each.

## The loop

Run in order. Restart at step 1 whenever a later step fails.

1. **Build** — `builderJoe` produces minimal, working code.
1. **Simplify** — `lazyJoe` flags over-engineering and bloat. Cut it, or route back to `builderJoe`.
1. **Document** — `docuJoe` documents the public surface.
1. **Test** — `testJoe` covers every branch, 100%, no unreachable code.
1. **Review** — `inspectorJoe` lists issues with location + one-line reason. Fix each, then re-run.
1. **Harden** — `secretJoe` hunts vulnerabilities. Fix or route to `builderJoe`.

## Exit gates

Ship only when ALL pass:

- `inspectorJoe` reports zero issues
- `testJoe` reports 100% coverage
- `secretJoe` finds nothing exploitable

Any gate failing sends the work back to the step that owns it. Keep looping until all three are green.

## Prompting agents

Prompt = work reference + user story or QED + explicit user instructions for the task. Nothing else. No task lists, no step-by-step, no output contracts.

Include what grounds the agent:

- Minimal file refs: `src/auth.ts`
- Prior review: `see review on PR #12` or `see <branch> diff: git diff main...branch`
- Goal: one user story sentence, exception message or expected behaviour (bugs only)
- Steps: QED, short, numbered bullets to reproduce the error
- Explicit user instructions for the task, verbatim.

Prompt shape:

```text
Work: <file(s)> or <PR/branch diff reference>
Goal: As a <role>, I want <capability>, so that <benefit>.
User said: <explicit instruction, verbatim>
```

or

```text
Work: <file(s)> or <PR/branch diff reference>
Goal: Should return boolean
Steps: 1. click this 2. click that 3. boom! QED
User said: <explicit instruction, verbatim>
```

## Agents

task -> agent

write minimal surgical code -> `builderJoe`
trim bloat / over-engineering -> `lazyJoe`
concise goal-oriented docs -> `docuJoe`
review minimalism/perf -> `inspectorJoe`
security research -> `secretJoe`
find & evaluate packages -> `researchJoe`
orchestrate the loop -> main thread

Rule: main thread loops; each agent does one step. Spawn `researchJoe` from any step when a dependency or fact needs checking; it never edits.

## Flow

```mermaid
sequenceDiagram
    participant Main as main thread
    participant B as builderJoe
    participant L as lazyJoe
    participant D as docuJoe
    participant T as testJoe
    participant I as inspectorJoe
    participant S as secretJoe

    Main->>B: build
    Main->>L: simplify
    L-->>Main: flags bloat (cut or route back)
    Main->>D: document
    loop until test 100%, review 0 issues, no exploits
        Main->>T: test
        Main->>I: review
        alt issues found
            Main->>B: fix
            Main->>T: re-test
            Main->>I: re-review
        end
        Main->>S: harden
        S-->>Main: exploits (or none)
    end
    Note over Main: ship only when all gates pass
```
