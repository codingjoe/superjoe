FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/joe-evals

COPY pyproject.toml uv.lock ./

COPY joe_evals ./joe_evals

RUN uv sync --locked

ENV JOE_EVALS_CONTAINER=1 \
    JOE_EVALS_ROOT=/work

WORKDIR /work

ENTRYPOINT ["/opt/joe-evals/.venv/bin/joe_evals"]
