from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import click
from docker.errors import DockerException
from testcontainers.core.container import DockerContainer
from testcontainers.core.docker_client import DockerClient
from testcontainers.core.image import DockerImage

IMAGE = "joe-evals:latest"

WORKSPACE = "/work"

CONTAINER_MARKER = "JOE_EVALS_CONTAINER"

PASSTHROUGH = ("OLLAMA_API_KEY", "OLLAMA_BASE_URL")

NOBODY = 65534


def in_container() -> bool:
    """Return whether the CLI already runs inside the eval image."""
    return os.environ.get(CONTAINER_MARKER) == "1"


def container_user() -> str | None:
    """Return the host uid and gid as a docker user, or None without one."""
    if not hasattr(os, "getuid"):
        return None
    return f"{os.getuid() or NOBODY}:{os.getgid() or NOBODY}"


def passed_env() -> dict[str, str]:
    """Return the credentials this environment passes into the container."""
    return {name: value for name in PASSTHROUGH if (value := os.environ.get(name))}


def creation_time(tag: str) -> datetime | None:
    """Return when the image was built, or None when it is absent or unreadable."""
    try:
        return datetime.fromisoformat(
            DockerClient().client.images.get(tag).attrs["Created"]
        )
    except (
        DockerException,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None


@contextmanager
def docker_failure() -> Iterator[None]:
    """Turn a docker client failure into one message the CLI can show."""
    try:
        yield
    except DockerException as error:
        raise click.ClickException(
            f"docker is unavailable: {error}; install Docker or start its daemon,"
            " then retry"
        ) from error


def ensure_image(root: Path, force: bool = False) -> str:
    """Return the eval image tag, building the image when it is stale."""
    inputs = [
        root / "Dockerfile",
        root / "pyproject.toml",
        root / "uv.lock",
        *(root / "joe_evals").rglob("*"),
    ]
    newest = max(
        (path.stat().st_mtime for path in inputs if path.exists()), default=0.0
    )
    built = creation_time(IMAGE)
    if force or built is None or built.timestamp() < newest:
        with docker_failure():
            DockerImage(path=root, tag=IMAGE, clean_up=False).build()
    return IMAGE


def launch(root: Path, args: Sequence[str]) -> int:
    """Run the eval image over `root` and return the container's exit code."""
    with docker_failure():
        container = DockerContainer(
            IMAGE,
            command=list(args),
            volumes=[(str(root), WORKSPACE, "rw")],
            working_dir=WORKSPACE,
            user=container_user(),
            env=passed_env(),
        )
        try:
            container.start()
            running = container.get_wrapped_container()
            for chunk in running.attach(
                stream=True, logs=True, stdout=True, stderr=True
            ):
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            return running.wait()["StatusCode"]
        finally:
            container.stop()
