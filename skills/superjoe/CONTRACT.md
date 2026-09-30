# The joe contract

Every joe run is a map or a reduce. Read this file before you report.

## Input contract

A prompt is an envelope, nothing else.

| Field        | Carries                                           |
| ------------ | ------------------------------------------------- |
| `Work:`      | the diff, file, PR, or branch to work             |
| `Goal:`      | one user story, or `Steps:` for a QED repro       |
| `Phase:`     | `triage`, `prove`, or `report`                    |
| `Shard:`     | the chunk this worker owns: `1/2 src/money.py`    |
| `Ledger:`    | the run's ledger path, or `none`                  |
| `Note:`      | where the reference note goes, or `none`          |
| `Mode:`      | `lite`, `full`, `ultra` for builders and trimmers |
| `User said:` | the user's own words, verbatim                    |

Missing `Work:` or `User said:`: `ambiguous. ask: <one question>.` Never guess the work.

## Output contract

One line per finding. No preamble, no summary, no prose between lines.

`<tag>: <lane> <what>. [<key>]`

The tag opens the line. No bullet, no number, no bold, no backtick around it: a
decorated line is not a finding line, and the ledger cannot read it.

| Field    | Carries                                                                                      |
| -------- | -------------------------------------------------------------------------------------------- |
| `<tag>`  | the verb, from the lane's own vocabulary: `sus`, `cap`, `real`, `fixed`, `deferred`, `clear` |
| `<lane>` | the routing key, one lane from the table below                                               |
| `<key>`  | one line, one finding: `[src/orders.py:L38]`, `[deps:pydantic-ai-harness]`                   |

Ratings ride the same line: `real: bug <what>. <why>. [src/orders.py:L38] bet: 9/10 cooked: 8/10`.
A `receipts:` block opens under the `real:` line above it and carries neither lane nor key.
A finding with no file, like a dependency, keys on its subject: `[deps:<pkg>]`, `[docs:<topic>]`.
A shard that maps clean closes with `clear: <lane> [shard:<path>] nothing to report.`, so
the reduce can prove every shard answered.

## Sharding

One shard, one worker, one context. A shard is a chunk a joe judges on its own, so no
worker loads what another worker loads.

- Unit: one file. Split a file only past ~200 changed lines, by function or region.
- Bundle: files under ~40 changed lines, so a shard earns its own prompt.
- Budget: 4 shards per lane, 6 workers in flight. Each worker pays prompt and ledger
  overhead, and the machine is shared. Raise it only for a genuinely big patch.
- Threshold: under 2 files or ~150 changed lines, do not shard; one prompt holds the lot.

`Shard: <n>/<total> <path>` names the chunk, and `Work:` points at that chunk's own
frozen diff. Read your diff and the file it touches. Never open a neighbour's shard: the
signatures you call are enough to judge your own lines.

- Triage stays in the shard: every `sus:`, `yeet:`, and `ghost:` line keys on a line the
  shard owns. Found something outside it? That is the neighbour's row, so leave it.
- Prove may leave it: a confirmed key may follow a call into another shard, and the
  reduce routes that finding to the shard that owns its key.
- A key outside every shard is out of scope: `side quest:`.
- A worker who must read three files to judge one line is in the wrong shard: move the
  boundary, or hand that key to the shard that owns it.

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

## Reference notes

Thorough research nobody can read again is work repeated twice. `researchJoe` writes what
it learns into `.claude/skills/joe-deps/`, so the crew stops re-asking and the repo keeps
the knowledge as a skill the next session loads.

- `SKILL.md` — the index, one line per subject: `pkg@version: verdict. what it solves.`
- `<subject>.md` — the note: `Verdict`, `API`, `Gotchas`, `Evidence`.
- Keyed `[deps:<pkg>]` or `[docs:<topic>]`, like its ledger row. One subject, one note:
  update it, never open a second.
- `Note: <path>` carries the subject's path. `Note: none` means the workspace is read-only,
  so hand the note back in the answer instead of writing it.

```markdown
# pydantic-ai-harness

## Verdict

Kept at 0.36.0, pushed 2026-09-12.

## API

`Coder(root)`, `Researcher()`, mounted as capabilities.

## Gotchas

Reads the whole tree unless the capability is scoped.

## Evidence

PyPI json, 2026-09-30.
```

The index opens with the skill's frontmatter, so the note set is discoverable:

```markdown
---
name: joe-deps
description: Vetted packages, APIs, and upstream docs for this repo, with the verdict and the calls that matter. Read before adding, hand-rolling, or reporting on one.
---

- pydantic-ai-harness@0.36.0: kept. Coder and Researcher capabilities. [note](pydantic-ai-harness.md)
```

`builderJoe` and `inspectorJoe` read the note before either of them researches, hand-rolls,
or reports on that subject: rung 5 of the ladder is the note, not a memory. No note and no
verdict? One `deps` request to `researchJoe`, once.

## The ledger

The main thread owns `.joe/ledger.md`, gitignored, one per run. Every joe reads it, no
joe but the main thread writes it.

```text
# work: main...feat base: 4f2a1b head: 9c3d2e patch: 2 files, +38
# shards: 1/2 src/money.py | 2/2 src/orders.py
sus  bug  src/orders.py:L27          bare except hides every failure
cap  sec  src/auth.py:L12            parameterized, `%` never sees user input
real bug  src/orders.py:L27          label returns str, caller unpacks a tuple   bet: 9/10 cooked: 8/10
clear bug shard:src/money.py         mapped clean
kept deps deps:pydantic-ai-harness   maintained, 0.36.0 pushed 2026-09 (pypi)   note: .claude/skills/joe-deps/pydantic-ai-harness.md
```

Rows: `<tag> <lane> <key> <what>.` One patch, one lookup, one row. A `side quest:` line
becomes a `deferred` row; a fix flips its row to `fixed`.

The main thread folds a line as it writes the row: strip a leading bullet, number, or
backtick, and bracket a bare `path:L<line>`. The wire format stays the agent's job and the
evals score it, but a decorated line costs a normalization, never a re-run.

## Dedupe

- Key = `[path:L<line>]`. Two lanes, one key, one finding: the first claim holds.
- One key, two lanes: the highest lane wins, `sec` > `bug` > `perf` > `bloat` > `doc` > `test` > `deps` > `naming`.
- A key the ledger holds is claimed: emit `cap: <lane> duplicate of [<key>].` and stop.
- Never emit the same key twice in a run.

## No repeat work

- The patch is frozen once, one diff per shard. Every worker reads its own chunk; nobody
  re-derives it, and nobody loads a chunk another worker already holds.
- One research request per question, keyed `[deps:<pkg>]` or `[docs:<topic>]`. Everyone
  else reads the row; nobody re-asks what the ledger answers.
- A fix re-opens its line and the lanes those lines open. Rows outside the fix stay valid.
