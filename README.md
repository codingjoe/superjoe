# superjoe

`codingjoe`'s digital clone — because one Joe wasn't enough. A
[Claude Code plugin](https://code.claude.com/docs/en/plugin-marketplaces) of AI
agents and skills, each representing a different alter ego of `codingjoe`.

## The crew

- **superjoe** — orchestrates two loops: architecture (build, simplify, document, review, harden), then testing
- **joe-audit** — audits the whole repo for over-engineering and hands back a ranked delete-list
- **joe-debt** — harvests `joe:` shortcut comments into a tracked ledger, so "later" doesn't become "never"
- **builderjoe** — writes code faster than `codingjoe` can say "it worked on my machine"
- **lazyjoe** — flags over-engineering and bloat, then delegates the cutting back
- **docujoe** — documents the public surface, and deletes the docstrings nobody asked for
- **testjoe** — covers every branch, 100%, and flags unreachable or defensive code for builderjoe to cut
- **inspectorjoe** — reviews code with the scrutiny of someone who's been burned by a missing semicolon
- **secretjoe** — finds your vulnerabilities before the bad guys do (no cape required)
- **researchjoe** — finds and evaluates packages so nobody re-implements one

## The crew, scored

```bash
export OLLAMA_API_KEY=...                       # Ollama Cloud key
uv run joe_evals
```

A local Ollama needs no key, and needs the daemon reachable from inside the
container:

```bash
OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    JOE_EVALS_MODEL=deepseek-v4.1-flash:cloud \
    JOE_EVALS_JUDGE=deepseek-v4.1-flash:cloud uv run joe_evals
```

That is the one command. It builds the image, mounts the repository at
`/work`, and executes the whole suite in the container, so no agent gets a
shell on this machine. `joe_evals_build` builds the image on its own.
`JOE_EVALS_MODEL`, `JOE_EVALS_JUDGE` and `JOE_EVALS_REPEATS` override
`models.yaml`; `JOE_EVALS_REPORT`, `JOE_EVALS_BASELINE` and
`JOE_EVALS_COMMENT` name the three files it writes, beside the sources.

### What a rating means

A case scores 0 to 100 across four axes, weighted like this:

- **Contract** (0.5) — `Contract`, `ToolDiscipline` and `WorkspaceDiff`
- **Cohesion** (0.2) — `Cohesion`, an LLM judge
- **Speed** (0.15) — `MaxDuration` and `ToolBudget`
- **Reliability** (0.15) — the share of a case's runs that reached the pass
  score

Every evaluator scores 0 to 1, an axis averages its evaluators and scales the
result to 100, and the case score is the weighted sum. An axis no case could
measure scores zero and keeps its weight, so every report reads on one scale:
a baseline with one repeat per case stays comparable with a labeled run with
three. The comment names the leftovers under `Unmeasured axes`. Reliability
needs repeats, so a single run leaves it at zero.

An agent's **rating** is the mean of its case scores. A case **passes** at 60
and **regresses** when it drops more than 2 points, or falls from a pass into a
failure.

### Add a case

The suite is `cases.yaml`, one pydantic-evals `Dataset` the CLI loads with
`Dataset.from_file`. A case is one entry, next to the fixtures it names:

```yaml
name: builderjoe-push-back
cases:
  - name: builderjoe-push-back
    inputs:
      agent: builderJoe
      prompt: |
        Work: src/webhooks/dispatch.py
        Goal: guard dispatch against bad payloads.
        User said: "add a plugin registry with an LRU cache."
      fixture: speculative-cache
      patch: change.diff
      script:
        bash:
          uv run pytest: |
            ============ 1 passed in 0.05s ============
        web_search:
          pydantic: Pydantic v2 is current.
        answer: No, keep it simple.
    evaluators:
      - Contract:
          required_patterns:
            - (?i)(no-code|YAGNI|side quest)
          forbidden_patterns: []
      - ToolDiscipline:
          required_tools: [Read]
          forbidden_tools: [Write, Edit]
          required_commands: [pytest]
          forbidden_commands: [pre-commit]
      - WorkspaceDiff:
          required_paths: []
          forbidden_paths: ['*']
      - MaxDuration:
          seconds: 150
      - ToolBudget:
          max_calls: 10
      - Cohesion: {}
```

`fixture` names a directory under `fixtures/`, and `patch` a diff inside it
that is applied before the agent starts. `script` replaces the outside world:
`bash` maps a command line to the output the agent reads back, `web_search` a
query substring to results, and `answer` answers every `AskUserQuestion`. A
command no entry matches runs in the container, and the call log marks the
scripted miss.

A required check is graded by fraction: miss one of four and you score 0.75. A
single violation zeroes its evaluator. A command pattern matches the command
from its first word, never an argument, so `grep pytest src/` is not a pytest
run; `uv run`, `python -m` and friends are skipped, and a `cd ... &&` in front
changes nothing.

### Add a model

`models.yaml` pins three things: `default_model` runs the agents, `judge_model`
scores cohesion (drop it and the judge falls back to the default model), and
`sweep` lists the models a full run covers. Score another model locally with
`JOE_EVALS_MODEL`, dispatch the `evals` workflow with its `model` input, or add
the name to `sweep` and label a pull request `run-evals-full` to run three
repeats of every swept model.

### What CI does

`.github/workflows/evals.yml` runs on pull requests and on `main` pushes that
touch `agents/`, `cases.yaml`, `fixtures/`, `joe_evals/`, `models.yaml` or
`pyproject.toml`. The run needs `OLLAMA_API_KEY`; a fork pull request gets no
secret, so only a branch of this repository reaches a keyed run.

The run splits into jobs, so no single one holds both the branch's code and a
write token. `evals` runs the branch's harness with `contents: read` and no
write token at all. `comment` owns `pull-requests: write`, checks out no branch
code, downloads the rendered comment artifact and posts it with inline `gh`
calls. It finds its own sticky comment by the `## superjoe evals` marker and the
`github-actions[bot]` author, so a comment that merely quotes the marker is
never patched.

The eval image builds in the workflow through `joe_evals_build`, in a step with
no secret in that step's environment. A pull request's `Dockerfile` therefore
runs where it can reach nothing the job holds, and the cases afterwards run in
the container `joe_evals` starts from that image.

The scores upload as the `evals-scores` artifact, one `scores-<model>.json` per
model. On a pull request the `comment` job posts or patches the
`## superjoe evals` comment — only when a rating moved or a case regressed —
and the `evals` job fails on a regression. The gate reads the baseline from the
`evals-scores` artifact of the last successful `main` run, so no branch carries
one and there is nothing in the repository to edit. A push to `main` uploads
the scores it just produced, so the next pull request diffs against a current
baseline.

### The container

The whole run happens in the image built from the root `Dockerfile`: the
harness, the model calls, and every command an agent runs. `joe_evals` starts
that container itself — the repository mounted at `/work`, the Ollama
variables, the `JOE_EVALS_*` overrides, and nothing else of yours — and removes
it when the run ends. That is the boundary, and no invocation of the suite
happens outside it. The paths in the container's output are that mount:
`/work/evals-report.json` is `evals-report.json` beside the sources.

Inside the container the agents get
[pydantic-ai-harness](https://pydantic.dev/docs/ai/harness/): `FileSystem`
under the names the prompts use (`Read`, `Grep`, `Write`, `Edit`) and `Shell`
as `Bash`. There is no per-command container and no network restriction on the
agent's shell, so what a case can reach is what the container can reach:

- the repository at `/work` is everything of yours a case can read, and all it
  can write
- the agent's shell cannot read `OLLAMA_API_KEY` or the other provider keys:
  the harness strips them from the environment it runs commands in
- `git` and `bash` are in the image; Python is not, so a case that needs test
  output scripts it

Files stay guarded, because a fixture and a patch come from a pull request: a
fixture is copied with its links kept as links, a fixture holding a link that
leaves it is refused, and a case's `fixture` has to stay inside the fixtures
tree while its `patch` stays inside the fixture. A scripted command never
reaches the shell at all.

## Credits

The ladder, the strict review notation, and the debt-ledger concept are
adapted from [ponytail](https://github.com/DietrichGebert/ponytail) (MIT).

## Installation

```text
/plugin marketplace add codingjoe/claude-plugins
/plugin install superjoe@codingjoe
```

## License

[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) — free as in "you can copy this, just don't pretend you wrote it"
