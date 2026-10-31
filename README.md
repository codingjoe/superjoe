# superjoe

`codingjoe`'s digital clone — because one Joe wasn't enough. A
[Claude Code plugin](https://code.claude.com/docs/en/plugin-marketplaces) of AI
agents and skills, each representing a different alter ego of `codingjoe`.

## The crew

- **superjoe-code**: writes minimal code and reviews it, then stops after killjoe for human review
- **superjoe-ship**: adds tests and docs after the review, then checks the ship gate
- **joe-audit** — audits the whole repo for over-engineering and hands back a ranked delete-list
- **builderjoe** — writes code faster than `codingjoe` can say "it worked on my machine"
- **killjoe**: removes the tests, docstrings, and comments builderjoe adds, before human review and after a cut in superjoe-ship
- **lazyjoe** — flags over-engineering and bloat, then delegates the cutting back
- **docujoe** — documents the public surface, and deletes the docstrings nobody asked for
- **testjoe** — covers every branch, 100%, and flags unreachable or defensive code for builderjoe to cut
- **inspectorjoe** — reviews code with the scrutiny of someone who's been burned by a missing semicolon
- **secretjoe** — finds your vulnerabilities before the bad guys do (no cape required)
- **researchjoe** — finds and evaluates packages so nobody re-implements one

## Two steps

Run `superjoe-code` to write and review the patch. It ends with `killjoe` and stops for
your review. After you approve the cleaned patch, run `superjoe-ship` to add tests and
docs.

## The contract

The crew works one frozen patch, sharded so one worker loads one chunk, one ledger at
`.cache/joe/ledger.md`, and one owner per finding, so no joe repeats another's read, lookup, or
question. Research lands as a note under `.cache/joe/deps/`, so `builderJoe` and
`inspectorJoe` read what `researchJoe` already proved. `killJoe` is the final step of
`superjoe-code`, after the review agents, and it runs again after `builderJoe` cuts in
`superjoe-ship`. The map, the reduce, and the one-line finding grammar are embedded in every
agent file and in [skills/superjoe-code/SKILL.md](skills/superjoe-code/SKILL.md), so a run
never reads outside the workspace.
[skills/superjoe-code/CONTRACT.md](skills/superjoe-code/CONTRACT.md) keeps the canonical
copy for maintainers.

## The crew, scored

Build the image once with `uv run joe_evals_build`, then run the suite with
`uv run joe_evals` and `OLLAMA_API_KEY` set. A local Ollama needs no key, only
`OLLAMA_BASE_URL=http://host.docker.internal:11434`.

## Credits

The ladder and the strict review notation are adapted from
[ponytail](https://github.com/DietrichGebert/ponytail) (MIT).

## Installation

```text
/plugin marketplace add codingjoe/claude-plugins
/plugin install superjoe@codingjoe
```

## License

[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/) — free as in "you can copy this, just don't pretend you wrote it"
