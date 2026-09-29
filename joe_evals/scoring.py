"""The recorded run, its rating, the baseline diff and the PR comment.

A run is recorded, never replayed: evaluators only ever read it. A case scores 0-100: each axis
averages its evaluator scores, the axes weigh in at `AXIS_WEIGHTS`, and an axis no case could
measure scores zero while keeping its weight. One formula for every report, so a baseline with
one repeat per case reads on the same scale as a labeled run with three.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field
from pydantic_evals.reporting import EvaluationReport, ReportCase, ReportCaseFailure

from .sandbox import AgentRun, CaseSpec

AXIS_WEIGHTS: dict[str, float] = {'contract': 0.5, 'cohesion': 0.2, 'speed': 0.15, 'reliability': 0.15}
"""Weight of each axis in the case score."""

AXIS_SIGNALS: dict[str, tuple[str, ...]] = {
    'contract': ('Contract', 'ToolDiscipline', 'WorkspaceDiff'),
    'cohesion': ('Cohesion',),
    'speed': ('MaxDuration', 'ToolBudget'),
}
"""Evaluator names behind each axis; reliability comes from the repeats instead."""

PASS_SCORE = 60.0
"""Case score a run must reach to count as a pass."""

REGRESSION_POINTS = 2.0
"""Drop in case score that counts as a regression."""

COMMENT_MARKER = '## superjoe evals'
"""Heading the sticky comment opens with; the workflow finds that comment by this marker *and* its author."""


class CaseScore(BaseModel):
    """One run of one case, scored."""

    name: str
    agent: str
    repeat: int = 1
    signals: dict[str, float] = Field(default_factory=dict)
    """Evaluator name to its 0-1 score."""
    reasons: dict[str, str] = Field(default_factory=dict)
    """Evaluator name to the line explaining its score."""
    axes: dict[str, float | None] = Field(default_factory=dict)
    """Axis to its 0-100 score; `None` marks an axis without enough runs to measure."""
    total: float = 0.0
    """Weighted 0-100 case score."""
    duration_secs: float = 0.0
    passed: bool = False
    text: str = ''
    """The agent's answer, kept for reading a regression; dropped from the baseline."""
    failure: str | None = None
    """Error message when the run itself raised."""


class RunReport(BaseModel):
    """The score artifact."""

    model: str
    created_at: datetime
    cases: list[CaseScore]
    ratings: dict[str, float]
    """Agent name to its mean case score."""

    def save(self, path: Path) -> None:
        """Write the artifact."""
        path.write_text(self.model_dump_json(indent=2) + '\n', encoding='utf-8')

    @classmethod
    def read(cls, path: Path) -> RunReport:
        """Read an artifact."""
        return cls.model_validate_json(path.read_text(encoding='utf-8'))

    def summary(self) -> RunReport:
        """The baseline shape: the same scores without the run text."""
        return self.model_copy(update={'cases': [case.model_copy(update={'text': ''}) for case in self.cases]})

    def failure(self) -> str | None:
        """Why this report cannot be trusted, or `None` when every case produced a score.

        A run nothing could be rated from is a broken harness, not a quiet zero: the caller
        fails on the message instead of reporting the calm of an empty report.
        """
        broken = [f'{case.name} (run {case.repeat}): {case.failure}' for case in self.cases if case.failure]
        if broken:
            return 'case runs failed:\n' + '\n'.join(broken)
        return None if self.ratings else 'no case produced a rating'


def axis_scores(signals: Mapping[str, float], reliability: float | None = None) -> dict[str, float | None]:
    """Average each axis' evaluator scores into 0-100."""
    axes: dict[str, float | None] = {
        axis: 100.0 * mean(values)
        for axis, names in AXIS_SIGNALS.items()
        if (values := [signals[name] for name in names if name in signals])
    }
    axes['reliability'] = None if reliability is None else 100.0 * reliability
    return axes


def case_score(axes: Mapping[str, float | None]) -> float:
    """Weight every axis into the 0-100 case score; an axis that was not measured scores zero."""
    return sum(AXIS_WEIGHTS[axis] * (score or 0.0) for axis, score in axes.items())


def evaluator_signals(run: ReportCase[CaseSpec, AgentRun, Any]) -> dict[str, float]:
    """The numeric evaluator results of one run, reasons dropped.

    A stock evaluator answers `bool`, which pydantic-evals files under the run's assertions
    rather than its scores, so the axes read both.
    """
    return {name: float(result.value) for name, result in (run.scores | run.assertions).items()}


def rate(report: EvaluationReport[CaseSpec, AgentRun, Any], model: str) -> RunReport:
    """Score every run of an evaluation report into the artifact."""
    cases = [row for group in group_cases(report) for row in score_case_runs(group)]
    return RunReport(
        model=model,
        created_at=datetime.now(tz=timezone.utc),
        cases=cases,
        ratings=ratings(cases),
    )


def ratings(cases: Iterable[CaseScore]) -> dict[str, float]:
    """Mean case score per agent, over the case runs that produced a score."""
    by_agent: dict[str, list[float]] = {}
    for case in cases:
        if case.failure is None:
            by_agent.setdefault(case.agent, []).append(case.total)
    return {agent: mean(scores) for agent, scores in sorted(by_agent.items())}


@dataclass(frozen=True)
class CaseRuns:
    """Every run of one case: what came back, and what raised."""

    name: str
    """Case name without the repeat suffix."""
    case: CaseSpec
    runs: tuple[ReportCase[CaseSpec, AgentRun, Any], ...]
    failures: tuple[ReportCaseFailure[CaseSpec, AgentRun, Any], ...]

    @property
    def count(self) -> int:
        """How often the case ran."""
        return len(self.runs) + len(self.failures)


def group_cases(report: EvaluationReport[CaseSpec, AgentRun, Any]) -> list[CaseRuns]:
    """Group a report by case, successes and failures together.

    pydantic-evals only groups repeated cases; `rate` wants the same view whether a case ran
    once or ten times.
    """
    inputs: dict[str, CaseSpec] = {}
    runs: dict[str, list[ReportCase[CaseSpec, AgentRun, Any]]] = {}
    failures: dict[str, list[ReportCaseFailure[CaseSpec, AgentRun, Any]]] = {}
    for result in (*report.cases, *report.failures):
        name = result.source_case_name or result.name
        inputs.setdefault(name, result.inputs)
        if isinstance(result, ReportCaseFailure):
            failures.setdefault(name, []).append(result)
        else:
            runs.setdefault(name, []).append(result)
    return [
        CaseRuns(name=name, case=case, runs=tuple(runs.get(name, ())), failures=tuple(failures.get(name, ())))
        for name, case in inputs.items()
    ]


def score_case_runs(group: CaseRuns) -> list[CaseScore]:
    """Score one case: a row per run, and a row per failed run.

    A run that raised is its own row and never a zero in the case mean: a repeat that failed
    counts against the case's reliability instead.
    """
    scores = [case_score(axis_scores(evaluator_signals(run))) for run in group.runs]
    reliability = sum(score >= PASS_SCORE for score in scores) / group.count if group.count > 1 else None
    return [
        score_run(group, run, repeat=repeat, reliability=reliability) for repeat, run in enumerate(group.runs, 1)
    ] + [
        CaseScore(name=group.name, agent=group.case.agent, repeat=repeat, failure=failure.error_message)
        for repeat, failure in enumerate(group.failures, len(group.runs) + 1)
    ]


def score_run(
    group: CaseRuns,
    run: ReportCase[CaseSpec, AgentRun, Any],
    repeat: int,
    reliability: float | None,
) -> CaseScore:
    """Score one run of one case."""
    signals = evaluator_signals(run)
    axes = axis_scores(signals, reliability)
    total = case_score(axes)
    return CaseScore(
        name=group.name,
        agent=group.case.agent,
        repeat=repeat,
        signals=signals,
        reasons={name: result.reason or '' for name, result in run.scores.items()},
        axes=axes,
        total=total,
        duration_secs=run.task_duration,
        passed=total >= PASS_SCORE,
        text=run.output.text,
    )


def case_means(report: RunReport) -> dict[str, float]:
    """Mean score per case name, over the runs that produced a score."""
    by_case: dict[str, list[float]] = {}
    for case in report.cases:
        if case.failure is None:
            by_case.setdefault(case.name, []).append(case.total)
    return {name: mean(scores) for name, scores in by_case.items()}


@dataclass(frozen=True)
class CaseDelta:
    """One case of the baseline against the same case now."""

    case: str
    agent: str
    before: float
    after: float

    @property
    def delta(self) -> float:
        """Score change."""
        return self.after - self.before

    @property
    def regressed(self) -> bool:
        """Whether the case dropped past the gate or past the regression budget."""
        return self.before - self.after > REGRESSION_POINTS or self.before >= PASS_SCORE > self.after


def case_deltas(baseline: RunReport, current: RunReport) -> list[CaseDelta]:
    """Every case in both reports, worst delta first."""
    before = case_means(baseline)
    agents = {case.name: case.agent for case in current.cases}
    deltas = [
        CaseDelta(case=name, agent=agents[name], before=before[name], after=score)
        for name, score in case_means(current).items()
        if name in before
    ]
    return sorted(deltas, key=lambda delta: delta.delta)


def regressions(baseline: RunReport, current: RunReport) -> list[CaseDelta]:
    """Cases that dropped against the baseline."""
    return [delta for delta in case_deltas(baseline, current) if delta.regressed]


def changed(baseline: RunReport, current: RunReport) -> bool:
    """Whether the comment is worth posting: a rating moved, or a case regressed."""
    before = {agent: round(rating, 1) for agent, rating in baseline.ratings.items()}
    after = {agent: round(rating, 1) for agent, rating in current.ratings.items()}
    return before != after or bool(regressions(baseline, current))


def render_comment(baseline: RunReport, current: RunReport) -> str:
    """The sticky PR comment: rating deltas per agent, plus the cases behind them."""
    deltas = case_deltas(baseline, current)
    broken = [delta for delta in deltas if delta.regressed]
    lines = [
        f'{COMMENT_MARKER} — `{current.model}`',
        '',
        '| Agent | Rating | Δ |',
        '| --- | --- | --- |',
        *(
            render_rating_row(agent, baseline.ratings.get(agent), rating)
            for agent, rating in sorted(current.ratings.items())
        ),
        '',
    ]
    if unmeasured := unmeasured_axes(current):
        lines += [f'Unmeasured axes: {", ".join(unmeasured)}.', '']
    if not baseline.cases:
        lines += ['No baseline yet — nothing to compare against.', '']
    elif broken:
        lines += ['### Regressions', '', *render_case_table(broken)]
    elif not current.ratings:
        lines += ['No case produced a rating; every case run failed.', '']
    elif current.cases:
        lines += ['No regressions.', '', '### Cases', '', *render_case_table(deltas)]
    return '\n'.join(lines) + '\n'


def unmeasured_axes(report: RunReport) -> list[str]:
    """Axes no case of the report could measure."""
    measured = {axis for case in report.cases for axis, score in case.axes.items() if score is not None}
    return sorted(set(AXIS_WEIGHTS) - measured) if report.cases else []


def render_case_table(deltas: Iterable[CaseDelta]) -> list[str]:
    """The markdown table of case deltas."""
    return [
        '| Case | Agent | Before | After | Δ |',
        '| --- | --- | --- | --- | --- |',
        *(
            f'| {delta.case} | {delta.agent} | {delta.before:.1f} | {delta.after:.1f} | {delta.delta:+.1f} |'
            for delta in deltas
        ),
        '',
    ]


def render_rating_row(agent: str, before: float | None, after: float) -> str:
    """One markdown row of the rating table; a new agent has no delta."""
    return f'| {agent} | {after:.1f} | {"new" if before is None else f"{after - before:+.1f}"} |'
