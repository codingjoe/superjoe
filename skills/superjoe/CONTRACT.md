# The joe contract

Every joe run is a map or a reduce. Read this file before you report.

## Input contract

A prompt is an envelope, nothing else.

| Field        | Carries                                           |
| ------------ | ------------------------------------------------- |
| `Work:`      | the diff, file, PR, or branch to work             |
| `Goal:`      | one user story, or `Steps:` for a QED repro       |
| `Phase:`     | `triage`, `prove`, or `report`                    |
| `Ledger:`    | the run's ledger path, or `none`                  |
| `Mode:`      | `lite`, `full`, `ultra` for builders and trimmers |
| `User said:` | the user's own words, verbatim                    |

Missing `Work:` or `User said:`: `ambiguous. ask: <one question>.` Never guess the work.

## Output contract

One line per finding. No preamble, no summary, no prose between lines.

`<tag>: <lane> <what>. [<key>]`

| Field    | Carries                                                                             |
| -------- | ----------------------------------------------------------------------------------- |
| `<tag>`  | the verb, from the lane's own vocabulary: `sus`, `cap`, `real`, `fixed`, `deferred` |
| `<lane>` | the routing key, one lane from the table below                                      |
| `<key>`  | one line, one finding: `[src/orders.py:L38]`, `[deps:pydantic-ai-harness]`          |

Ratings ride the same line: `real: bug <what>. <why>. [src/orders.py:L38] bet: 9/10 cooked: 8/10`.
A `receipts:` block opens under the `real:` line above it and carries neither lane nor key.
A finding with no file, like a dependency, keys on its subject: `[deps:<pkg>]`, `[docs:<topic>]`.

## Lanes

The lane picks the owner. Any joe may tag any lane: a finding outside your lane costs
one line, emit it and move on.

| Lane     | Owner        | Tags                                  | Work                                |
| -------- | ------------ | ------------------------------------- | ----------------------------------- |
| `sec`    | secretJoe    | `sus` `cap` `real` `receipts`         | exploitability                      |
| `bug`    | inspectorJoe | `sus` `cap` `real`                    | correctness                         |
| `perf`   | inspectorJoe | `sus` `cap` `real`                    | speed and memory                    |
| `naming` | inspectorJoe | `sus` `cap` `real`                    | names and readability               |
| `bloat`  | lazyJoe      | `yeet` `duh` `NPC` `cringe` `glow up` | over-engineering and dead code      |
| `doc`    | docuJoe      | `yeet` `real`                         | docstrings, comments, README        |
| `test`   | testJoe      | `ghost` `delulu`                      | coverage, ghost and delulu branches |
| `deps`   | researchJoe  | `kept` `dropped`                      | packages, APIs, upstream docs       |

## The ledger

The main thread owns `.joe/ledger.md`, gitignored, one per run. Every joe reads it, no
joe but the main thread writes it.

```text
# work: main...feat base: 4f2a1b head: 9c3d2e patch: 1 file, +38
sus  bug  src/orders.py:L27          bare except hides every failure
cap  sec  src/auth.py:L12            parameterized, `%` never sees user input
real bug  src/orders.py:L27          label returns str, caller unpacks a tuple   bet: 9/10 cooked: 8/10
kept deps deps:pydantic-ai-harness   maintained, 0.36.0 pushed 2026-09 (pypi)
```

Rows: `<tag> <lane> <key> <what>.` One patch, one lookup, one row. A `side quest:` line
becomes a `deferred` row; a fix flips its row to `fixed`.

## Dedupe

- Key = `[path:L<line>]`. Two lanes, one key, one finding: the first claim holds.
- One key, two lanes: the highest lane wins, `sec` > `bug` > `perf` > `bloat` > `doc` > `test` > `deps` > `naming`.
- A key the ledger holds is claimed: emit `cap: <lane> duplicate of [<key>].` and stop.
- Never emit the same key twice in a run.

## No repeat work

- The patch is frozen once. Every mapper works the same reference; nobody re-derives it.
- One research request per question, keyed `[deps:<pkg>]` or `[docs:<topic>]`. Everyone
  else reads the row; nobody re-asks what the ledger answers.
- A fix re-opens its line and the lanes those lines open. Rows outside the fix stay valid.
