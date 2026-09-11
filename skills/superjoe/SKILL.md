---
name: superJoe
description: Orchestration for joe's agent crew.
---

SuperJoe = a crew. Use it as two **iterative loops**, not a one-shot dispatch: architecture first, then testing. The main thread runs the loops; agents do one step each.

## The architecture loop

Run in order. Restart at step 1 whenever a later step fails.

1. **Build** — `builderJoe` produces minimal, working code.
1. **Simplify** — `lazyJoe` flags over-engineering and bloat. Cut it, or route back to `builderJoe`.
1. **Document** — `docuJoe` documents the public surface and deletes docstrings nobody asked for.
1. **Review** — `inspectorJoe` triages to `suspicion:` lines, the user confirms, it rates `confidence: N/10` and `impact: N/10`. Fix both axes at `8/10` or above, then re-run.
1. **Harden** — `secretJoe` triages to `suspicion:` lines, the user confirms, it proves and rates them. Route both axes at `8/10` or above to `builderJoe`.

## Exit gates

Ship only when both loops pass.

Architecture: no in-scope finding at `8/10` or above on both axes, nothing exploitable in scope.

Testing: 100% coverage, every flagged branch cut.

Only `8/10` or above on both axes blocks the gate. Everything else: the user approves it, or it is deferred. A failing gate sends the work back to its owner.

## The confirmation gate

`inspectorJoe` and `secretJoe` run two phases. The user sits between them.

1. **Triage** — emit `suspicion:` lines. `secretJoe` proves nothing here.
1. **Confirm** — ask the user which to investigate. Nothing runs unconfirmed.
1. **Investigation** — confirm or drop each one, then rate the survivors.

| confidence | impact | Action                           |
| ---------- | ------ | -------------------------------- |
| `>= 8`     | `>= 8` | fix now; blocks the gate         |
| `>= 8`     | `< 8`  | fix if small, otherwise `defer:` |
| `< 8`      | `>= 8` | ask the user                     |
| `< 8`      | `< 8`  | report only                      |

## The testing loop

Its own loop, prompted once the architecture loop is green, never a step inside it.

1. `testJoe` writes tests, hits 100% coverage, flags unreachable branches and checks the signature already guarantees. It edits no production code.
1. `lazyJoe` tags each flag `delete:`.
1. `builderJoe` cuts it.

Every cut re-runs coverage. Any production change reopens the review and harden gates.

## Findings

Every agent reports a finding once. Route on the first line that matches:

| Finding                         | Route                                              |
| ------------------------------- | -------------------------------------------------- |
| suspicion                       | triage only; the user confirms first               |
| cleared suspicion (`dropped:`)  | route nothing                                      |
| `8/10` or above on both axes    | fix it, re-run the owning step                     |
| confidence `>= 8`, impact `< 8` | fix if small, otherwise `defer:`                   |
| confidence `< 8`                | ask the user; never fix, never gate                |
| out of scope (`defer:`)         | file a GitHub issue, change nothing                |
| vulnerability                   | `secretJoe`; nobody else reports one               |
| bug, performance, naming        | `inspectorJoe`; nobody else reports one            |
| over-engineering, dead code     | `lazyJoe`; nobody else reports one                 |
| uncovered lines                 | `testJoe`; nobody else reports them                |
| unreachable or defensive branch | `testJoe` flags, `lazyJoe` tags, `builderJoe` cuts |

## Out-of-scope findings

Deferred, never fixed:

1. The reviewer emits one `defer: <what>. <why>. [path]` line.
1. The main thread files one `gh issue create`, quoting the line, the repo, and the work reference.
1. No other agent touches it, or any out-of-scope code it notices.

`joe-audit` and `joe-debt` are exempt: their repo-wide list is the deliverable.

## Modes

The crew simplifies at one of three levels. Default: **full**. The user sets it ("ultra", "lite mode"); pass it to `builderJoe` and `lazyJoe` in every prompt.

| Mode  | builderJoe                                                                      | lazyJoe                                                       |
| ----- | ------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| lite  | Builds what's asked; names the lazier alternative in one line.                  | Flags only clear rung violations.                             |
| full  | The ladder enforced: YAGNI -> reuse -> stdlib -> native -> one line -> minimum. | Flags every rung violation.                                   |
| ultra | YAGNI extremist: deletion before addition; challenges the requirement itself.   | Flags speculative anything, including tests beyond one check. |

## One-shot reports

Outside the loop, on request:

- `joe-audit` — whole-repo over-engineering audit, ranked list of what to delete.
- `joe-debt` — harvest `joe:` shortcut comments into a tracked ledger.

## Prompting agents

Prompt = work reference + user story or QED + explicit user instructions for the task. Nothing else. No task lists, no step-by-step, no output contracts.

Include what grounds the agent:

- Minimal file refs: `src/auth.ts`
- Scope: the work reference bounds the review; anything else gets a `defer:` line
- Prior review: `see review on PR #12` or `see <branch> diff: git diff main...branch`
- Goal: one user story sentence, exception message or expected behaviour (bugs only)
- Steps: QED, short, numbered bullets to reproduce the error
- Phase: reviewer prompts ask for triage; investigation waits for user confirmation.
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
tests, coverage, unreachable branches -> `testJoe`, in the testing loop after review
find & evaluate packages -> `researchJoe`
orchestrate the loops -> main thread

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
    participant U as user

    Main->>B: build
    Main->>L: simplify
    L-->>Main: flags bloat (cut or route back)
    Main->>D: document
    loop until review clean, no exploits
        Main->>I: review
        I->>U: suspicions
        U->>I: confirm what to investigate
        alt 8/10 or above on both axes
            Main->>B: fix
            Main->>I: re-review
        else below 8/10 on either axis, or out of scope
            Main->>U: ask the user or file an issue
        end
        Main->>S: harden
        S->>U: suspicions
        U->>S: confirm what to prove
        S-->>Main: proven exploits (or none)
    end
    Note over Main: architecture green, prompt testJoe
    loop until coverage 100%
        Main->>T: test
        T-->>Main: flags unreachable and defensive branches
        Main->>L: cut verdict
        Main->>B: cut
        Main->>I: re-review changed code
    end
    Note over Main: ship only when both loops pass
```
