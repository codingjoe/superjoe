import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRetries, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.hooks import Hooks
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.tools import Tool, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import LLM_API_KEY_ENV_PATTERNS, Shell
from pydantic_evals import Case, Dataset

from .agents import AgentSpec, build_model

COMMAND_TIMEOUT_SECS = 60

RETRY_DELAY_SECS = 5

RUNNER_PREFIXES: tuple[str, ...] = (
    "uv run ",
    "uvx ",
    "python -m ",
    "python3 -m ",
    "sudo ",
    "env ",
    "time ",
)

UNKNOWN_SEARCH = "No search results available in the eval sandbox."

UNKNOWN_ANSWER = "No answer available in the eval sandbox."

HARNESS_TOOLS: dict[str, str] = {
    "Read": "read_file",
    "Grep": "search_files",
    "Write": "write_file",
    "Edit": "edit_file",
    "Bash": "run_command",
}

DENIED_SHELL_ENV: tuple[str, ...] = (*LLM_API_KEY_ENV_PATTERNS, "OLLAMA_*")


class ToolScript(BaseModel):
    bash: dict[str, str] = Field(
        default_factory=dict,
        description="Command line to its output; anything else runs in the shell.",
    )
    web_search: dict[str, str] = Field(
        default_factory=dict,
        description="Query substring to the canned results it returns.",
    )
    answer: str = Field(
        default=UNKNOWN_ANSWER, description="Answer to every AskUserQuestion call."
    )


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


@dataclass(frozen=True)
class AgentRun:
    text: str
    tool_calls: tuple[ToolCall, ...]
    changed_paths: tuple[str, ...]


def normalize_command(command: str) -> str:
    line = " ".join(command.split())
    while runner := next(
        (runner for runner in RUNNER_PREFIXES if line.startswith(runner)), None
    ):
        line = line[len(runner) :].lstrip()
    return line


def shell_commands(line: str) -> tuple[str, ...]:
    return tuple(
        command
        for segment in re.split(r"[;&|\n]+", line)
        if (command := normalize_command(segment))
    )


def scripted_output(script: ToolScript, command: str) -> str | None:
    commands = shell_commands(command)
    entries = sorted(
        ((normalize_command(key), output) for key, output in script.bash.items()),
        key=lambda entry: -len(entry[0]),
    )
    for key, output in entries:
        if any(
            candidate == key or candidate.startswith(f"{key} ")
            for candidate in commands
        ):
            return output
    return None


async def record_tool_call(
    ctx: RunContext[SandboxDeps],
    *,
    call: ToolCallPart,
    tool_def: ToolDefinition,
    args: dict[str, Any],
    handler: Callable[[dict[str, Any]], Awaitable[Any]],
) -> Any:
    command = args.get("command")
    scripted = (
        scripted_output(ctx.deps.script, command)
        if call.tool_name == "Bash" and isinstance(command, str)
        else None
    )
    try:
        if scripted is not None:
            result = scripted
        else:
            result = await handler(args)
            if call.tool_name == "Bash" and ctx.deps.script.bash:
                result = f"[scripted miss: no entry matched]\n{result}"
    except Exception as error:
        ctx.deps.log.record(call.tool_name, args, f"{type(error).__name__}: {error}")
        raise
    ctx.deps.log.record(call.tool_name, args, str(result))
    return result


def web_search(ctx: RunContext[SandboxDeps], query: str) -> str:
    """
    Search the web, with the case scripting every result.

    Args:
        ctx: The run this tool was called in.
        query: Search query.

    """
    return next(
        (
            text
            for key, text in ctx.deps.script.web_search.items()
            if key.lower() in query.lower()
        ),
        UNKNOWN_SEARCH,
    )


def ask_user_question(ctx: RunContext[SandboxDeps], question: str) -> str:
    """
    Ask the user, with the case scripting the answer.

    Args:
        ctx: The run this tool was called in.
        question: Question to ask.

    """
    return ctx.deps.script.answer


SCRIPTED_TOOLS: dict[str, Tool[SandboxDeps]] = {
    "WebSearch": Tool(web_search, name="WebSearch"),
    "AskUserQuestion": Tool(ask_user_question, name="AskUserQuestion"),
}


def rename_map(tools: Sequence[str]) -> dict[str, str]:
    """Return the public names of the harness tools an agent was granted."""
    return {public: inner for public, inner in HARNESS_TOOLS.items() if inner in tools}


@dataclass
class RenamingToolset(WrapperToolset[SandboxDeps]):
    """
    Rename tools for the model, keeping the public name on `ctx.tool_name`.

    `RenamedToolset` rewrites `ctx.tool_name` to the original name on the way in,
    which hides the tool from the run's registry and stops the harness emitting
    its capability events.
    """

    name_map: dict[str, str]

    async def get_tools(
        self, ctx: RunContext[SandboxDeps]
    ) -> dict[str, ToolsetTool[SandboxDeps]]:
        inverse = {inner: public for public, inner in self.name_map.items()}
        return {
            inverse.get(name, name): replace(
                tool,
                toolset=self,
                tool_def=replace(tool.tool_def, name=inverse.get(name, name)),
            )
            for name, tool in (await self.wrapped.get_tools(ctx)).items()
        }

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[SandboxDeps],
        tool: ToolsetTool[SandboxDeps],
    ) -> Any:
        original = self.name_map.get(name, name)
        return await self.wrapped.call_tool(
            original,
            tool_args,
            ctx,
            replace(tool, tool_def=replace(tool.tool_def, name=original)),
        )


@dataclass
class RenamedFileSystem(FileSystem[SandboxDeps]):
    """The harness file tools under the names the joe prompts use."""

    def get_toolset(self) -> AbstractToolset[SandboxDeps]:
        return RenamingToolset(super().get_toolset(), rename_map(self.tools))


@dataclass
class RenamedShell(Shell[SandboxDeps]):
    """The harness shell under the name the joe prompts use."""

    def get_toolset(self) -> AbstractToolset[SandboxDeps]:
        return RenamingToolset(super().get_toolset(), {"Bash": "run_command"})


def build_agent(spec: AgentSpec, model: Model, root: Path) -> Agent[SandboxDeps, str]:
    """Assemble the agent under test from its prompt, its tools and the sandbox root."""
    names = (
        (*HARNESS_TOOLS, *SCRIPTED_TOOLS) if spec.tools is None else tuple(spec.tools)
    )
    harness = {name: HARNESS_TOOLS[name] for name in names if name in HARNESS_TOOLS}
    capabilities: list[AbstractCapability[SandboxDeps]] = []
    if file_tools := [tool for tool in harness.values() if tool != "run_command"]:
        capabilities.append(
            RenamedFileSystem(root_dir=root, tools=file_tools, content_hashes=False)
        )
    if harness.get("Bash"):
        capabilities.append(
            RenamedShell(
                cwd=root,
                tools=["run_command"],
                default_timeout=COMMAND_TIMEOUT_SECS,
                denied_env_patterns=DENIED_SHELL_ENV,
                allow_interactive=False,
            )
        )
    agent = Agent(
        model,
        deps_type=SandboxDeps,
        name=spec.name,
        description=spec.description,
        instructions=spec.instructions,
        tools=[tool for name, tool in SCRIPTED_TOOLS.items() if name in names],
        capabilities=[*capabilities, Hooks(tool_execute=record_tool_call)],
        retries=AgentRetries(tools=3),
    )
    agent.instrument = True
    return agent


def read_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.readlink().encode()
        if path.is_symlink()
        else path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }


@dataclass(frozen=True)
class Sandbox:
    root: Path
    original: Mapping[str, bytes]
    temporary: tempfile.TemporaryDirectory[str]

    @classmethod
    def create(cls, fixture: Path, patch: Path | None = None) -> Sandbox:
        temporary = tempfile.TemporaryDirectory(prefix="joe-evals-")
        root = Path(temporary.name)
        shutil.copytree(fixture, root, dirs_exist_ok=True, symlinks=True)
        if patch is not None:
            subprocess.run(["git", "apply", str(patch.resolve())], cwd=root, check=True)
        return cls(root=root, original=read_tree(root), temporary=temporary)

    def changed_paths(self) -> tuple[str, ...]:
        current = read_tree(self.root)
        changed = (self.original.keys() ^ current.keys()) | {
            path
            for path in self.original.keys() & current.keys()
            if self.original[path] != current[path]
        }
        return tuple(sorted(changed))

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.temporary.cleanup()


class CaseSpec(BaseModel):
    agent: str = Field(description="Agent name, spelled as its frontmatter spells it.")
    prompt: str = Field(description="Task prompt handed to the agent.")
    fixture: str = Field(description="Fixture directory copied into the sandbox.")
    patch: str | None = Field(
        default=None, description="Diff inside the fixture, applied to the copy."
    )
    script: ToolScript = Field(
        default_factory=ToolScript, description="Canned answers for the scripted tools."
    )


class CaseDataset(Dataset[CaseSpec, AgentRun, Any]):
    """The whole suite as one dataset."""


@dataclass(frozen=True)
class CaseRunner:
    agents: Mapping[str, AgentSpec]
    model_name: str
    fixtures: Path

    def validate(self, cases: Sequence[Case[CaseSpec, AgentRun, Any]]) -> None:
        broken = [
            f"{case.name}: {problem}"
            for case in cases
            if (problem := self.problem(case))
        ]
        if broken:
            raise ValueError("cannot run these cases:\n" + "\n".join(broken))

    def paths(self, case: CaseSpec) -> tuple[Path, Path | None]:
        fixture = self.fixtures / case.fixture
        return fixture, fixture / case.patch if case.patch else None

    def problem(self, case: Case[CaseSpec, AgentRun, Any]) -> str:
        if case.inputs.agent not in self.agents:
            return f"unknown agent {case.inputs.agent}"
        fixture, patch = self.paths(case.inputs)
        if not fixture.is_dir():
            return f"missing fixture {case.inputs.fixture}"
        if patch is not None and not patch.is_file():
            return f"missing patch {case.inputs.patch}"
        return ""

    def run(self, case: CaseSpec) -> AgentRun:
        try:
            return self.run_in_sandbox(case)
        except AgentRunError:
            time.sleep(RETRY_DELAY_SECS)
            return self.run_in_sandbox(case)

    def run_in_sandbox(self, case: CaseSpec) -> AgentRun:
        fixture, patch = self.paths(case)
        with Sandbox.create(fixture, patch) as sandbox:
            deps = SandboxDeps(root=sandbox.root, script=case.script, log=ToolCallLog())
            agent = build_agent(
                self.agents[case.agent], build_model(self.model_name), sandbox.root
            )
            result = agent.run_sync(case.prompt, deps=deps)
            return AgentRun(
                text=result.output,
                tool_calls=tuple(deps.log.calls),
                changed_paths=sandbox.changed_paths(),
            )
