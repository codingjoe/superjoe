import fnmatch
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from pydantic_ai.models import Model
from pydantic_evals.evaluators import (
    EvaluationReason,
    Evaluator,
    EvaluatorContext,
    LLMJudge,
    MaxDuration,
    MaxToolCalls,
    OutputConfig,
)

from .sandbox import AgentRun, CaseSpec, shell_commands


def grade_checks(
    required: Mapping[str, bool], violations: Sequence[str]
) -> EvaluationReason:
    if violations:
        return EvaluationReason(value=0.0, reason=f"violation: {violations[0]}")
    missing = [name for name, met in required.items() if not met]
    if not missing:
        return EvaluationReason(value=1.0, reason="all required checks met")
    return EvaluationReason(
        value=1.0 - len(missing) / len(required),
        reason=f"missing: {', '.join(missing)}",
    )


def any_path_matches(names: Iterable[str], patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for name in names for pattern in patterns)


def run_commands(run: AgentRun) -> tuple[str, ...]:
    return tuple(
        command
        for call in run.tool_calls
        if call.name == "Bash"
        for command in shell_commands(call.arguments["command"])
    )


def command_matches(commands: Iterable[str], patterns: Iterable[str]) -> bool:
    return any(
        re.match(pattern, command) for command in commands for pattern in patterns
    )


@dataclass
class Contract(Evaluator):
    required_patterns: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()

    def evaluate(
        self, ctx: EvaluatorContext[CaseSpec, AgentRun, Any]
    ) -> EvaluationReason:
        text = ctx.output.text
        return grade_checks(
            {
                f"/{pattern}/": bool(re.search(pattern, text))
                for pattern in self.required_patterns
            },
            [
                f"/{pattern}/"
                for pattern in self.forbidden_patterns
                if re.search(pattern, text)
            ],
        )


@dataclass
class ToolDiscipline(Evaluator):
    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_commands: tuple[str, ...] = ()
    forbidden_commands: tuple[str, ...] = ()

    def evaluate(
        self, ctx: EvaluatorContext[CaseSpec, AgentRun, Any]
    ) -> EvaluationReason:
        run = ctx.output
        used = [call.name for call in run.tool_calls]
        commands = run_commands(run)
        required = {f"tool {name}": name in used for name in self.required_tools} | {
            f"command /{pattern}/": command_matches(commands, (pattern,))
            for pattern in self.required_commands
        }
        violations = [
            f"tool {name}" for name in self.forbidden_tools if name in used
        ] + [
            f"command {command}"
            for command in commands
            if command_matches((command,), self.forbidden_commands)
        ]
        return grade_checks(required, violations)


@dataclass
class WorkspaceDiff(Evaluator):
    required_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()

    def evaluate(
        self, ctx: EvaluatorContext[CaseSpec, AgentRun, Any]
    ) -> EvaluationReason:
        changed = ctx.output.changed_paths
        return grade_checks(
            {
                f"change {pattern}": any_path_matches(changed, (pattern,))
                for pattern in self.required_paths
            },
            [
                path
                for path in changed
                if any_path_matches((path,), self.forbidden_paths)
            ],
        )


DEFAULT_RUBRIC = (
    "Score how well the answer holds together as one piece of work for the task: does it answer "
    "the task, keep one goal and one voice, and read as a finished report instead of a pile of "
    "loose observations? 1 means every part serves the task, 0 means the answer drifts off it "
    "or contradicts itself."
)


@dataclass(repr=False)
class Cohesion(LLMJudge):
    rubric: str = DEFAULT_RUBRIC
    include_input: bool = True
    score: OutputConfig | Literal[False] = field(
        default_factory=lambda: OutputConfig(
            evaluation_name="Cohesion", include_reason=True
        )
    )
    assertion: OutputConfig | Literal[False] = False


def with_judge(
    evaluators: Iterable[Evaluator], judge_model: Model | str
) -> list[Evaluator]:
    return [
        replace(evaluator, model=judge_model)
        if isinstance(evaluator, Cohesion)
        else evaluator
        for evaluator in evaluators
    ]


EVALUATORS: tuple[type[Evaluator], ...] = (
    Contract,
    ToolDiscipline,
    WorkspaceDiff,
    MaxDuration,
    MaxToolCalls,
    Cohesion,
)
