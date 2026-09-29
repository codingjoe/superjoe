FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /opt/joe-evals

COPY pyproject.toml uv.lock ./

COPY joe_evals ./joe_evals

RUN uv sync --locked

ENV JOE_EVALS_CONTAINER=1 \
    JOE_EVALS_ROOT=/work

WORKDIR /work

ENTRYPOINT ["/opt/joe-evals/.venv/bin/joe_evals"]
