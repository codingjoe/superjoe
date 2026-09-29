"""Evaluators over one recorded run.

The contract axis comes from `Contract`, `ToolDiscipline` and `WorkspaceDiff`; cohesion from
`Cohesion`, the stock `LLMJudge` under this suite's rubric; speed from the stock `MaxDuration`
and the local `ToolBudget`. Reliability is not an evaluator: it comes from the repeats, so
`scoring` reads it off the report instead.

Our own evaluators return a number; the stock `MaxDuration` answers `bool`, which pydantic-evals
files under the run's assertions rather than its scores.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from pydantic_ai.models import Model
from pydantic_evals.evaluators import (
    EvaluationReason,
    Evaluator,
    EvaluatorContext,
    LLMJudge,
    MaxDuration,
    OutputConfig,
)

from .sandbox import AgentRun, shell_commands

if TYPE_CHECKING:
    from .sandbox import CaseSpec


def grade_checks(required: Mapping[str, bool], violations: Sequence[str]) -> EvaluationReason:
    """Grade required checks by fraction; a single violation zeroes the score."""
    if violations:
        return EvaluationReason(value=0.0, reason=f'violation: {violations[0]}')
    missing = [name for name, met in required.items() if not met]
    if not missing:
        return EvaluationReason(value=1.0, reason='all required checks met')
    return EvaluationReason(value=1.0 - len(missing) / len(required), reason=f'missing: {", ".join(missing)}')


def any_path_matches(names: Iterable[str], patterns: Iterable[str]) -> bool:
    """Whether any path matches any glob pattern."""
    return any(fnmatch.fnmatch(name, pattern) for name in names for pattern in patterns)


def run_commands(run: AgentRun) -> tuple[str, ...]:
    """Every command the run's `Bash` calls ran, runner prefixes aside.

    A case pattern matches the command from its first word, never an argument, so `grep pytest
    src/` is not a pytest run. A command behind `uv run`, `python -m` or a `cd ... &&` still is.
    """
    return tuple(
        command
        for call in run.tool_calls
        if call.name == 'Bash'
        for command in shell_commands(call.arguments['command'])
    )


def command_matches(commands: Iterable[str], patterns: Iterable[str]) -> bool:
    """Whether any command is one of the patterns."""
    return any(re.match(pattern, command) for command in commands for pattern in patterns)


@dataclass
class Contract(Evaluator):
    """Required and forbidden regular expressions in the agent's answer."""

    required_patterns: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()

    def evaluate(self, ctx: EvaluatorContext[CaseSpec, AgentRun, Any]) -> EvaluationReason:
        """Score the answer against the case's output contract."""
        text = ctx.output.text
        return grade_checks(
            {f'/{pattern}/': bool(re.search(pattern, text)) for pattern in self.required_patterns},
            [f'/{pattern}/' for pattern in self.forbidden_patterns if re.search(pattern, text)],
        )


@dataclass
class ToolDiscipline(Evaluator):
    """Which tools a run used, and which command lines it ran."""

    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_commands: tuple[str, ...] = ()
    forbidden_commands: tuple[str, ...] = ()

    def evaluate(self, ctx: EvaluatorContext[CaseSpec, AgentRun, Any]) -> EvaluationReason:
        """Score the run against the case's tool rules."""
        run = ctx.output
        used = [call.name for call in run.tool_calls]
        commands = run_commands(run)
        required = {f'tool {name}': name in used for name in self.required_tools} | {
            f'command /{pattern}/': command_matches(commands, (pattern,)) for pattern in self.required_commands
        }
        violations = [f'tool {name}' for name in self.forbidden_tools if name in used] + [
            f'command {command}' for command in commands if command_matches((command,), self.forbidden_commands)
        ]
        return grade_checks(required, violations)


@dataclass
class WorkspaceDiff(Evaluator):
    """The files a run changed in its sandbox.

    Patterns are globs; `*` also crosses directory separators.
    """

    required_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()

    def evaluate(self, ctx: EvaluatorContext[CaseSpec, AgentRun, Any]) -> EvaluationReason:
        """Score the run against the case's diff rules."""
        changed = ctx.output.changed_paths
        return grade_checks(
            {f'change {pattern}': any_path_matches(changed, (pattern,)) for pattern in self.required_paths},
            [path for path in changed if any_path_matches((path,), self.forbidden_paths)],
        )


@dataclass
class ToolBudget(Evaluator):
    """The number of tool calls a run may spend."""

    max_calls: int = 12

    def evaluate(self, ctx: EvaluatorContext[CaseSpec, AgentRun, Any]) -> EvaluationReason:
        """Score the run against its tool-call budget."""
        count = len(ctx.output.tool_calls)
        return EvaluationReason(
            value=1.0 if count <= self.max_calls else 0.0,
            reason=f'{count} calls of {self.max_calls}',
        )


DEFAULT_RUBRIC = (
    'Score how well the answer holds together as one piece of work for the task: does it answer '
    'the task, keep one goal and one voice, and read as a finished report instead of a pile of '
    'loose observations? 1 means every part serves the task, 0 means the answer drifts off it '
    'or contradicts itself.'
)
"""The rubric `Cohesion` judges with, on the stock judge's 0-1 score."""


@dataclass(repr=False)
class Cohesion(LLMJudge):
    """Cohesion, scored by an LLM judge.

    The stock judge under `DEFAULT_RUBRIC`, shown the case's inputs and the run they produced.
    Its score keeps the name `Cohesion` and its reason; nothing is asserted. `with_judge` points
    its `model` at the judge the CLI runs.
    """

    rubric: str = DEFAULT_RUBRIC
    include_input: bool = True
    score: OutputConfig | Literal[False] = field(
        default_factory=lambda: OutputConfig(evaluation_name='Cohesion', include_reason=True)
    )
    assertion: OutputConfig | Literal[False] = False


def with_judge(evaluators: Iterable[Evaluator], judge_model: Model | str) -> list[Evaluator]:
    """Point every cohesion judge at `judge_model`."""
    return [
        replace(evaluator, model=judge_model) if isinstance(evaluator, Cohesion) else evaluator
        for evaluator in evaluators
    ]


EVALUATORS: tuple[type[Evaluator], ...] = (
    Contract,
    ToolDiscipline,
    WorkspaceDiff,
    MaxDuration,
    ToolBudget,
    Cohesion,
)
"""Every evaluator a case file may configure, in the order the docs list them."""
