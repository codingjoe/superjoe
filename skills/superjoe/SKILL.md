---
name: superJoe
description: Orchestration for joe's agent crew.
---

Superjoe = a crew of specialized agents for high-quality, minimalist, and secure code.

## When to use superjoe vs alternatives

| Task                                                     | Use            |
| -------------------------------------------------------- | -------------- |
| Write minimal, high-quality code / Surgical edits        | `builderjoe`   |
| Trim unnecessary code / guard against over-engineering   | `lazyjoe`      |
| Write or update concise, goal-oriented documentation     | `docujoe`      |
| Review code for minimalism, architecture, or performance | `inspectorjoe` |
| Uncover vulnerabilities and perform security research    | `secretjoe`    |
| Read docs / find & evaluate packages on indexes          | `researchjoe`  |
| Complex orchestration / High-level design                | Main thread    |

Rule of thumb: Use the specialized agents for targeted tasks to maintain high quality and minimalism.

## Why this exists (the real win)

By delegating to specialized "joe" agents, the main thread ensures that every piece of code is written by a builder (`builderjoe`), trimmed of anything unnecessary by a lazy guard (`lazyjoe`), documented precisely (`docujoe`), reviewed for architecture and performance (`inspectorjoe`), and vetted for security (`secretjoe`). This prevents bloat and security regressions.

## Output contracts

What main thread can rely on per agent:

**`builderjoe`**
Minimalist implementation, following `naming-things` guidelines, with 100% test coverage.

**`lazyjoe`**
Flags unnecessary code and work another joe owns, routing each to the right agent. Does no writing itself.

**`docujoe`**
Concise, imperative documentation in present tense, focused on the user's goals.

**`inspectorjoe`**
Bullet-point list of issues with location and one-sentence reasoning, focusing on minimalism and security.

**`secretjoe`**
Minimal step-by-step proof (QeD) of a vulnerability and a brief explanation of the exploit.

**`researchjoe`**
Ranked table of candidate packages with health, license, and fit; cites sources. Spawnable by any agent.
