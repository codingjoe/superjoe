import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from docker.errors import DockerException, ImageNotFound
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage

IMAGE = "joe-evals:latest"

WORKSPACE = "/work"

HARNESS_DIR = ".pydantic-ai-harness"

CONTAINER_MARKER = "JOE_EVALS_CONTAINER"

PASSTHROUGH = (
    "OLLAMA_API_KEY",
    "OLLAMA_BASE_URL",
    "JOE_EVALS_MODEL",
    "JOE_EVALS_JUDGE",
    "JOE_EVALS_REPEATS",
)

NOBODY = 65534


def in_container() -> bool:
    return os.environ.get(CONTAINER_MARKER) == "1"


def container_user() -> str | None:
    if not hasattr(os, "getuid"):
        return None
    return f"{os.getuid() or NOBODY}:{os.getgid() or NOBODY}"


def passed_env() -> dict[str, str]:
    return {name: value for name in PASSTHROUGH if (value := os.environ.get(name))}


@contextmanager
def docker_failure() -> Iterator[None]:
    try:
        yield
    except ImageNotFound as error:
        sys.stderr.write(
            f"the eval image {IMAGE} is missing: build it with joe_evals_build\n"
        )
        raise SystemExit(1) from error
    except DockerException as error:
        sys.stderr.write(
            f"docker is unavailable: {error}; install Docker or start its daemon,"
            " then retry\n"
        )
        raise SystemExit(1) from error


def build_image(root: Path) -> str:
    with docker_failure():
        DockerImage(path=root, tag=IMAGE, clean_up=False).build()
    return IMAGE


@contextmanager
def harness_mountpoint(root: Path) -> Iterator[None]:
    # A nested mount needs its mountpoint to exist in the read-only bind source.
    path = root / HARNESS_DIR
    created = not path.exists()
    if created:
        path.mkdir()
    try:
        yield
    finally:
        if created:
            path.rmdir()


def launch(root: Path) -> int:
    with harness_mountpoint(root), docker_failure():
        container = DockerContainer(
            IMAGE,
            volumes=[(str(root), WORKSPACE, "ro")],
            working_dir=WORKSPACE,
            user=container_user(),
            env=passed_env(),
        )
        # The container runs as the host user, so the tmpfs needs a writable mode.
        container.tmpfs[f"{WORKSPACE}/{HARNESS_DIR}"] = "rw,mode=1777"
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
