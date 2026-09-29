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

## The contract

The crew works one frozen patch, one ledger at `.joe/ledger.md`, and one owner per
finding, so no joe repeats another's read, lookup, or question. The map, the reduce,
and the one-line finding grammar live in [CONTRACT.md](CONTRACT.md).

## The crew, scored

Build the image once with `uv run joe_evals_build`, then run the suite with
`uv run joe_evals` and `OLLAMA_API_KEY` set. A local Ollama needs no key, only
`OLLAMA_BASE_URL=http://host.docker.internal:11434`.

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
