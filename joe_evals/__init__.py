"""The superjoe eval harness.

Each `agents/*.md` file becomes a pydantic-ai agent, runs in a sandbox that never touches the
host shell or the network, and is scored on contract, cohesion, speed and reliability.
"""
