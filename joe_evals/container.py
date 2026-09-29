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

CONTAINER_MARKER = "JOE_EVALS_CONTAINER"

PASSTHROUGH = (
    "OLLAMA_API_KEY",
    "OLLAMA_BASE_URL",
    "JOE_EVALS_MODEL",
    "JOE_EVALS_JUDGE",
    "JOE_EVALS_REPEATS",
    "JOE_EVALS_REPORT",
    "JOE_EVALS_BASELINE",
    "JOE_EVALS_COMMENT",
)

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


@contextmanager
def docker_failure() -> Iterator[None]:
    """Turn a docker client failure into one message the CLI can show."""
    try:
        yield
    except ImageNotFound as error:
        raise SystemExit(
            f"the eval image {IMAGE} is missing: build it with joe_evals_build"
        ) from error
    except DockerException as error:
        raise SystemExit(
            f"docker is unavailable: {error}; install Docker or start its daemon,"
            " then retry"
        ) from error


def build_image(root: Path) -> str:
    """Build the eval image from the Dockerfile in `root`."""
    with docker_failure():
        DockerImage(path=root, tag=IMAGE, clean_up=False).build()
    return IMAGE


def launch(root: Path) -> int:
    """Run the eval image over `root` and return the container's exit code."""
    with docker_failure():
        container = DockerContainer(
            IMAGE,
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
