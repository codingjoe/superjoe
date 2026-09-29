import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRetries, RunContext
from pydantic_ai.capabilities import AbstractCapability, WebSearch
from pydantic_ai.capabilities.hooks import Hooks
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.tools import Tool, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset, ToolsetTool, WrapperToolset
from pydantic_ai_harness import AskUser
from pydantic_ai_harness.ask_user import AskUserAnswer, AskUserRequest, AskUserResponse
from pydantic_ai_harness.filesystem import FileSystem
from pydantic_ai_harness.shell import LLM_API_KEY_ENV_PATTERNS, Shell
from pydantic_evals import Case, Dataset

from .agents import AgentSpec, build_model

COMMAND_TIMEOUT_SECS = 60

RUNNER_PREFIXES: tuple[str, ...] = (
    "uv run ",
    "uvx ",
    "python -m ",
    "python3 -m ",
    "sudo ",
    "env ",
    "time ",
)


HARNESS_TOOLS: dict[str, str] = {
    "Read": "read_file",
    "Grep": "search_files",
    "Write": "write_file",
    "Edit": "edit_file",
    "Bash": "run_command",
}

DENIED_SHELL_ENV: tuple[str, ...] = (*LLM_API_KEY_ENV_PATTERNS, "OLLAMA_*")


class MissingScriptError(Exception):
    def __init__(self, what: str) -> None:
        super().__init__(f"nothing scripted for {what}")


class MissingAnswerError(MissingScriptError):
    def __init__(self) -> None:
        super().__init__("the user's answer")


class ToolScript(BaseModel):
    bash: dict[str, str] = Field(
        default_factory=dict,
        description="Command line to its output; anything else runs in the shell.",
    )
    web_search: dict[str, str] = Field(
        default_factory=dict,
        description="Query substring to the canned results it returns.",
    )
    answer: str | None = Field(
        default=None, description="Answer to every AskUserQuestion call."
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
    for key, answers in ctx.deps.script.web_search.items():
        if key.lower() in query.lower():
            return answers
    raise MissingScriptError(query)


def rename_map(tools: Sequence[str]) -> dict[str, str]:
    return {public: inner for public, inner in HARNESS_TOOLS.items() if inner in tools}


@dataclass
class RenamingToolset(WrapperToolset[SandboxDeps]):
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
    def get_toolset(self) -> AbstractToolset[SandboxDeps]:
        return RenamingToolset(super().get_toolset(), rename_map(self.tools))


@dataclass
class RenamedAskUser(AskUser[SandboxDeps]):
    def get_toolset(self) -> AbstractToolset[SandboxDeps]:
        return RenamingToolset(
            super().get_toolset(), {"AskUserQuestion": "ask_user_question"}
        )


@dataclass
class RenamedShell(Shell[SandboxDeps]):
    def get_toolset(self) -> AbstractToolset[SandboxDeps]:
        return RenamingToolset(super().get_toolset(), {"Bash": "run_command"})


SCRIPTED_TOOLS: tuple[str, ...] = ("WebSearch", "AskUserQuestion")


def scripted_answerer(
    script: ToolScript,
) -> Callable[[AskUserRequest], Awaitable[AskUserResponse]]:
    async def answers(request: AskUserRequest) -> AskUserResponse:
        if script.answer is None:
            raise MissingAnswerError
        return AskUserResponse(
            answers=tuple(
                AskUserAnswer(header=question.header, custom_answer=script.answer)
                for question in request.questions
            )
        )

    return answers


def build_agent(
    spec: AgentSpec, model: Model, root: Path, script: ToolScript
) -> Agent[SandboxDeps, str]:
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
    if "WebSearch" in names:
        capabilities.append(
            WebSearch(native=False, local=Tool(web_search, name="WebSearch"))
        )
    if "AskUserQuestion" in names:
        capabilities.append(RenamedAskUser(answerer=scripted_answerer(script)))
    agent = Agent(
        model,
        deps_type=SandboxDeps,
        name=spec.name,
        description=spec.description,
        instructions=spec.instructions,
        capabilities=[*capabilities, Hooks(tool_execute=record_tool_call)],
        retries=AgentRetries(tools=0),
    )
    agent.instrument = True
    return agent


class CaseSpec(BaseModel):
    agent: str = Field(description="Agent name, spelled as its frontmatter spells it.")
    prompt: str = Field(description="Task prompt handed to the agent.")
    fixture: str = Field(description="Fixture directory the agent works in.")
    script: ToolScript = Field(
        default_factory=ToolScript, description="Canned answers for the scripted tools."
    )


class CaseDataset(Dataset[CaseSpec, AgentRun, Any]):
    pass


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

    def fixture_path(self, case: CaseSpec) -> Path:
        return self.fixtures / case.fixture

    def problem(self, case: Case[CaseSpec, AgentRun, Any]) -> str:
        if case.inputs.agent not in self.agents:
            return f"unknown agent {case.inputs.agent}"
        if not self.fixture_path(case.inputs).is_dir():
            return f"missing fixture {case.inputs.fixture}"
        return ""

    def run(self, case: CaseSpec) -> AgentRun:
        root = self.fixture_path(case)
        deps = SandboxDeps(root=root, script=case.script, log=ToolCallLog())
        agent = build_agent(
            self.agents[case.agent],
            build_model(self.model_name),
            root,
            case.script,
        )
        result = agent.run_sync(case.prompt, deps=deps)
        return AgentRun(text=result.output, tool_calls=tuple(deps.log.calls))
