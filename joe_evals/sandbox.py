from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import timedelta
from functools import wraps
from pathlib import Path
from typing import Any

from docker.errors import ImageNotFound
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.tools import Tool
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator
from testcontainers.core.container import DockerContainer
from testcontainers.core.docker_client import DockerClient
from testcontainers.core.image import DockerImage

from .agents import AgentSpec, build_model

SANDBOX_IMAGE = 'joe-evals-sandbox:latest'

WORKSPACE = '/workspace'

NOBODY_ID = '65534'

TIMEOUT_SECS = 60

TIMEOUT_EXIT_CODE = 124

MEMORY_LIMIT = '512m'
CPU_LIMIT_NANOS = 1_000_000_000
PID_LIMIT = 128

RETRY_DELAY_SECS = 5

MAX_LINES = 2000

MAX_MATCHES = 200

RUNNER_PREFIXES: tuple[str, ...] = ('uv run ', 'uvx ', 'python -m ', 'python3 -m ', 'sudo ', 'env ', 'time ')

UNKNOWN_SEARCH = 'No search results available in the eval sandbox.'

UNKNOWN_ANSWER = 'No answer available in the eval sandbox.'


@dataclass(frozen=True)
class AgentRun:
    text: str
    tool_calls: tuple[ToolCall, ...]
    duration: timedelta
    changed_paths: tuple[str, ...]


@contextmanager
def build_sandbox_image() -> Iterator[None]:
    try:
        DockerClient().client.images.get(SANDBOX_IMAGE)
    except ImageNotFound:
        image = DockerImage(path=Path(__file__).parent, tag=SANDBOX_IMAGE)
    else:
        image = nullcontext()
    with image:
        yield


def container_user() -> str:
    return f'{os.getuid() or NOBODY_ID}:{os.getgid() or NOBODY_ID}'


def render_result(stdout: str, stderr: str, exit_code: int) -> str:
    if exit_code == TIMEOUT_EXIT_CODE:
        stderr = f'killed after {TIMEOUT_SECS}s\n{stderr}'
    return f'exit code {exit_code}\nstdout:\n{stdout.rstrip()}\nstderr:\n{stderr.rstrip()}'


def run_command(command: str, root: Path) -> str:
    container = (
        DockerContainer(SANDBOX_IMAGE, command=['timeout', str(TIMEOUT_SECS), 'bash', '-c', command])
        .with_volume_mapping(root, WORKSPACE, 'rw')
        .with_tmpfs_mount('/tmp')
        .with_kwargs(
            network_mode='none',
            read_only=True,
            cap_drop=['ALL'],
            security_opt=['no-new-privileges'],
            pids_limit=PID_LIMIT,
            mem_limit=MEMORY_LIMIT,
            nano_cpus=CPU_LIMIT_NANOS,
            user=container_user(),
            working_dir=WORKSPACE,
        )
    )
    with container:
        exit_code = container.wait()
        stdout, stderr = container.get_logs()
    return render_result(stdout.decode(errors='replace'), stderr.decode(errors='replace'), exit_code)


def normalize_command(command: str) -> str:
    line = ' '.join(command.split())
    while runner := next((runner for runner in RUNNER_PREFIXES if line.startswith(runner)), None):
        line = line[len(runner) :].lstrip()
    return line


def shell_commands(line: str) -> tuple[str, ...]:
    return tuple(command for segment in re.split(r'[;&|\n]+', line) if (command := normalize_command(segment)))


def scripted_output(script: ToolScript, command: str) -> str | None:
    commands = shell_commands(command)
    entries = sorted(
        ((normalize_command(key), output) for key, output in script.bash.items()), key=lambda entry: -len(entry[0])
    )
    for key, output in entries:
        if any(candidate == key or candidate.startswith(f'{key} ') for candidate in commands):
            return output
    return None


class ToolScript(BaseModel):
    bash: dict[str, str] = Field(
        default_factory=dict, description='Command line to its output; anything else runs in the container.'
    )
    web_search: dict[str, str] = Field(
        default_factory=dict, description='Query substring to the canned results it returns.'
    )
    answer: str = Field(default=UNKNOWN_ANSWER, description='Answer to every AskUserQuestion call.')


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: str


@dataclass
class ToolCallLog:
    calls: list[ToolCall] = field(default_factory=list)

    def record(self, name: str, arguments: dict[str, Any], result: str) -> None:
        self.calls.append(ToolCall(name, arguments, result))


@dataclass(frozen=True)
class SandboxDeps:
    root: Path
    script: ToolScript
    log: ToolCallLog


def report_errors_to_model(tool: Callable[..., str]) -> Callable[..., str]:
    @wraps(tool)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return tool(*args, **kwargs)
        except (OSError, ValueError, re.error) as error:
            return f'{type(error).__name__}: {error}'

    return wrapper


def resolve(root: Path, path: str) -> Path:
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f'{path} is outside the sandbox')
    return resolved


def read(ctx: RunContext[SandboxDeps], path: str, offset: int = 1, limit: int = MAX_LINES) -> str:
    """Read a file from the workspace.

    Args:
        path: File path relative to the workspace root.
        offset: First line to read, counted from 1.
        limit: Maximum number of lines to read.
    """
    lines = resolve(ctx.deps.root, path).read_text(encoding='utf-8').splitlines()
    selected = lines[offset - 1 : offset - 1 + limit]
    result = '\n'.join(f'{number:>6}\t{line}' for number, line in enumerate(selected, offset))
    ctx.deps.log.record('Read', {'path': path, 'offset': offset, 'limit': limit}, result)
    return result


def grep(ctx: RunContext[SandboxDeps], pattern: str, path: str = '.') -> str:
    """Search the workspace with a regular expression.

    Args:
        pattern: Regular expression to search for.
        path: File or directory to search, relative to the workspace root.
    """
    root = ctx.deps.root.resolve()
    target = resolve(root, path)
    files = (
        [target]
        if target.is_file()
        else [resolve(root, str(file.relative_to(root))) for file in sorted(target.rglob('*')) if file.is_file()]
    )
    regex = re.compile(pattern)
    matches = [
        f'{file.relative_to(root)}:{number}: {line}'
        for file in files
        for number, line in enumerate(file.read_text(encoding='utf-8').splitlines(), 1)
        if regex.search(line)
    ]
    result = '\n'.join(matches[:MAX_MATCHES]) or 'No matches.'
    ctx.deps.log.record('Grep', {'pattern': pattern, 'path': path}, result)
    return result


def write(ctx: RunContext[SandboxDeps], path: str, content: str) -> str:
    """Write a file in the workspace, creating directories as needed.

    Args:
        path: File path relative to the workspace root.
        content: Full file content.
    """
    file = resolve(ctx.deps.root, path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding='utf-8')
    result = f'Wrote {path}'
    ctx.deps.log.record('Write', {'path': path, 'content': content}, result)
    return result


def edit(
    ctx: RunContext[SandboxDeps],
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Replace an exact string in a workspace file.

    Args:
        path: File path relative to the workspace root.
        old_string: Text to replace.
        new_string: Replacement text.
        replace_all: Replace every occurrence instead of the first one.
    """
    file = resolve(ctx.deps.root, path)
    text = file.read_text(encoding='utf-8')
    if old_string in text:
        file.write_text(text.replace(old_string, new_string, -1 if replace_all else 1), encoding='utf-8')
        result = f'Edited {path}'
    else:
        result = f'{path}: old_string not found'
    ctx.deps.log.record(
        'Edit',
        {'path': path, 'old_string': old_string, 'new_string': new_string, 'replace_all': replace_all},
        result,
    )
    return result


def bash(ctx: RunContext[SandboxDeps], command: str) -> str:
    """Run a shell command: the case's script wins, anything else runs in a throwaway container.

    Args:
        command: Command line for the shell inside the container.
    """
    scripted = scripted_output(ctx.deps.script, command)
    if scripted is None:
        result = run_command(command, ctx.deps.root)
        if ctx.deps.script.bash:
            result = f'[scripted miss: no entry matched, ran in the sandbox container]\n{result}'
    else:
        result = scripted
    ctx.deps.log.record('Bash', {'command': command}, result)
    return result


def web_search(ctx: RunContext[SandboxDeps], query: str) -> str:
    """Search the web. Nothing leaves the machine: the case scripts the results.

    Args:
        query: Search query.
    """
    result = next(
        (text for key, text in ctx.deps.script.web_search.items() if key.lower() in query.lower()),
        UNKNOWN_SEARCH,
    )
    ctx.deps.log.record('WebSearch', {'query': query}, result)
    return result


def ask_user_question(ctx: RunContext[SandboxDeps], question: str) -> str:
    """Ask the user a question. The case scripts the answer.

    Args:
        question: Question to ask.
    """
    result = ctx.deps.script.answer
    ctx.deps.log.record('AskUserQuestion', {'question': question}, result)
    return result


TOOLS: dict[str, Tool[SandboxDeps]] = {
    tool.name: tool
    for tool in (
        Tool(report_errors_to_model(read), name='Read'),
        Tool(report_errors_to_model(grep), name='Grep'),
        Tool(report_errors_to_model(write), name='Write'),
        Tool(report_errors_to_model(edit), name='Edit'),
        Tool(bash, name='Bash'),
        Tool(web_search, name='WebSearch'),
        Tool(ask_user_question, name='AskUserQuestion'),
    )
}


def build_agent(spec: AgentSpec, model: Model) -> Agent[SandboxDeps, str]:
    names = tuple(TOOLS) if spec.tools is None else spec.tools
    return Agent(
        model,
        deps_type=SandboxDeps,
        name=spec.name,
        description=spec.description,
        instructions=spec.instructions,
        tools=[TOOLS[name] for name in names],
    )


def read_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
        for path in root.rglob('*')
        if path.is_file() or path.is_symlink()
    }


@dataclass(frozen=True)
class Sandbox:
    root: Path
    original: Mapping[str, bytes]
    temporary: tempfile.TemporaryDirectory[str]

    @classmethod
    def create(cls, fixture: Path, patch: Path | None = None) -> Sandbox:
        fixture = fixture.resolve()
        escaping = [
            link for link in fixture.rglob('*') if link.is_symlink() and not link.resolve().is_relative_to(fixture)
        ]
        if escaping:
            links = ', '.join(str(link.relative_to(fixture)) for link in escaping)
            raise ValueError(f'fixture links outside itself: {links}')
        temporary = tempfile.TemporaryDirectory(prefix='joe-evals-')
        root = Path(temporary.name)
        shutil.copytree(fixture, root, dirs_exist_ok=True, symlinks=True)
        if patch is not None:
            subprocess.run(['git', 'apply', str(patch.resolve())], cwd=root, check=True)
        return cls(root=root, original=read_tree(root), temporary=temporary)

    def changed_paths(self) -> tuple[str, ...]:
        current = read_tree(self.root)
        changed = (self.original.keys() ^ current.keys()) | {
            path for path in self.original.keys() & current.keys() if self.original[path] != current[path]
        }
        return tuple(sorted(changed))

    def __enter__(self) -> Sandbox:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.temporary.cleanup()


class CaseSpec(BaseModel):
    agent: str = Field(description='Agent name, spelled as its frontmatter spells it.')
    prompt: str = Field(description='Task prompt handed to the agent.')
    fixture: str = Field(description='Fixture directory copied into the sandbox.')
    patch: str | None = Field(default=None, description='Diff inside the fixture, applied to the copy.')
    script: ToolScript = Field(default_factory=ToolScript, description='Canned answers for the scripted tools.')


class CaseDataset(Dataset[CaseSpec, AgentRun, Any]):
    @classmethod
    def read(cls, paths: Iterable[Path], evaluator_types: Sequence[type[Evaluator]]) -> CaseDataset:
        datasets = [cls.from_file(path, custom_evaluator_types=evaluator_types) for path in paths]
        dataset = cls(
            name='superjoe',
            cases=[case for source in datasets for case in source.cases],
            evaluators=[evaluator for source in datasets for evaluator in source.evaluators],
        )
        ungraded = [case.name for case in dataset.cases if not case.evaluators and not dataset.evaluators]
        if ungraded:
            raise ValueError(f'cases without a single evaluator: {", ".join(ungraded)}')
        return dataset


@dataclass(frozen=True)
class CaseRunner:
    agents: Mapping[str, AgentSpec]
    model_name: str
    fixtures: Path

    def validate(self, cases: Sequence[Case[CaseSpec, AgentRun, Any]]) -> None:
        broken = [f'{case.name}: {problem}' for case in cases if (problem := self.problem(case))]
        if broken:
            raise ValueError('cannot run these cases:\n' + '\n'.join(broken))

    def resolve_paths(self, case: CaseSpec) -> tuple[Path, Path | None]:
        fixture = resolve(self.fixtures, case.fixture)
        return fixture, resolve(fixture, case.patch) if case.patch else None

    def problem(self, case: Case[CaseSpec, AgentRun, Any]) -> str:
        if case.inputs.agent not in self.agents:
            return f'unknown agent {case.inputs.agent}'
        try:
            fixture, patch = self.resolve_paths(case.inputs)
        except ValueError as error:
            return str(error)
        if not fixture.is_dir():
            return f'missing fixture {case.inputs.fixture}'
        if patch is not None and not patch.is_file():
            return f'missing patch {case.inputs.patch}'
        return ''

    def run(self, case: CaseSpec) -> AgentRun:
        try:
            return self.run_in_sandbox(case)
        except Exception:
            time.sleep(RETRY_DELAY_SECS)
            return self.run_in_sandbox(case)

    def run_in_sandbox(self, case: CaseSpec) -> AgentRun:
        fixture, patch = self.resolve_paths(case)
        with Sandbox.create(fixture, patch) as sandbox:
            deps = SandboxDeps(root=sandbox.root, script=case.script, log=ToolCallLog())
            started_at = time.monotonic()
            result = build_agent(self.agents[case.agent], build_model(self.model_name)).run_sync(case.prompt, deps=deps)
            duration = timedelta(seconds=time.monotonic() - started_at)
            return AgentRun(
                text=result.output,
                tool_calls=tuple(deps.log.calls),
                duration=duration,
                changed_paths=sandbox.changed_paths(),
            )
