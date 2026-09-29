"""
The rules that score the joe crew on its input and output contracts.

A rule reads a finished run: the prompt it was given, the output it produced, how
long it took, and the tool calls it made. Assertions gate a run, scores only report
a trend, and each rule here is one of the two and never both. Pass `RULES` as
`custom_evaluator_types` to `Dataset` to use them in a case file.
"""

import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

# pydantic-evals keeps its span heuristics private. A rename breaks this import loudly,
# and uv.lock pins the version that ships it.
from pydantic_evals.evaluators.agentic import _extract_tool_calls, _ToolCallInfo
from pydantic_evals.otel import SpanTreeRecordingError

_NO_SPANS = "no span tree: instrumentation is off, so tool calls are invisible"

# Assistant-speak no joe has any business writing.
_FILLER: tuple[str, ...] = (
    "i'd be happy to",
    "happy to help",
    "great question",
    "sure thing",
    "let me know if",
    "i hope this helps",
    "as an ai",
    "it's important to note",
    "it's worth noting",
    "please note that",
    "keep in mind that",
    "when it comes to",
    "at the end of the day",
    "in order to",
    "first and foremost",
    "delve into",
    "ever-evolving",
    "a testament to",
    "in today's fast-paced",
)

_PROMPT_LINES = ("Work:", "User said:")

_PROMPT_ALTERNATIVES = ("Goal:", "Steps:")

# The lane table of CONTRACT.md: the lane on a finding routes it to its owner.
_LANES = frozenset(("sec", "bug", "perf", "naming", "bloat", "doc", "test", "deps"))

# The tags a finding line may open with, longest first so `glow up` wins over `glow`.
_FINDING_TAGS = (
    "glow up",
    "deferred",
    "dropped",
    "delulu",
    "cringe",
    "fixed",
    "sus",
    "cap",
    "real",
    "yeet",
    "duh",
    "npc",
    "ghost",
    "kept",
)

_FINDING = re.compile(
    r"^(?P<tag>" + "|".join(_FINDING_TAGS) + r"):\s*(?P<lane>[A-Za-z]+)\b",
    re.IGNORECASE,
)

# One atomic key per finding: `[src/orders.py:L38]`, `[deps:pydantic-ai-harness]`.
# Key-shaped means a colon and no whitespace, so `list[dict]` in the prose is not one.
_KEY = re.compile(r"\[(?P<key>[^\[\]\s:]+:[^\[\]\s]+)\]")


def _starts(lines: Sequence[str], prefix: str) -> bool:
    return any(line.startswith(prefix) for line in lines)


def _words(text: str) -> int:
    return len(text.split())


def _ratio(target: float, actual: float) -> float:
    """Score a measurement against its target, losing marks in proportion above it."""
    return 1.0 if actual <= target else target / actual


def _normalized(text: str) -> str:
    return text.replace("\u2019", "'").lower()


def _listed(values: str | Sequence[str]) -> tuple[str, ...]:
    """Normalize a rule's pattern list, so one pattern needs no list around it."""
    return (values,) if isinstance(values, str) else tuple(values)


def _tool_calls(
    ctx: EvaluatorContext[object, object, object],
) -> list[_ToolCallInfo] | None:
    """Return every tool call of the run, or None when spans were not recorded."""
    try:
        span_tree = ctx.span_tree
    except SpanTreeRecordingError:
        return None
    return _extract_tool_calls(span_tree, include_failed=True)


def _argument_text(arguments: str | None) -> str:
    """Render a call's arguments as one line, for reasons and repeat detection."""
    if arguments is None:
        return ""
    try:
        parsed = json.loads(arguments)
    except ValueError:
        return arguments
    if isinstance(parsed, dict):
        return " ".join(str(value) for value in parsed.values())
    return arguments


@dataclass(repr=False)
class PromptContract(Evaluator[object, object, object]):
    """
    Assert the case input carries the crew's prompt shape.

    Every prompt a joe receives is a work reference, a goal or QED steps, and the
    user's own words. A case that skips one scores a prompt nobody would send. A
    phase that maps or proves adds its own fields through `extra`.
    """

    extra: Sequence[str] = ()

    def __post_init__(self) -> None:
        self.extra = _listed(self.extra) if self.extra else ()

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        lines = [line.strip() for line in str(ctx.inputs).splitlines()]
        wanted = (*_PROMPT_LINES, *(f"{field.rstrip(':')}:" for field in self.extra))
        missing = [prefix for prefix in wanted if not _starts(lines, prefix)]
        if not any(_starts(lines, prefix) for prefix in _PROMPT_ALTERNATIVES):
            missing.append(" or ".join(_PROMPT_ALTERNATIVES))
        if missing:
            return EvaluationReason(
                value=False, reason=f"prompt is missing {', '.join(missing)}"
            )
        return EvaluationReason(value=True)


@dataclass(repr=False)
class FindingContract(Evaluator[object, object, object]):
    """
    Assert every finding line carries a lane and its own key.

    A finding is one line: the lane routes it to an owner, the key keeps two
    agents off the same line. A line that drops either one cannot join the ledger,
    and a key that repeats is the same work done twice.
    """

    min_findings: int = 1

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        findings = [
            (line.strip(), match)
            for line in str(ctx.output).splitlines()
            if (match := _FINDING.match(line.strip()))
        ]
        if len(findings) < self.min_findings:
            return EvaluationReason(
                value=False,
                reason=f"{len(findings)} finding line(s), min={self.min_findings}",
            )
        stray = sorted(
            {
                match.group("lane").lower()
                for _, match in findings
                if match.group("lane").lower() not in _LANES
            }
        )
        if stray:
            return EvaluationReason(
                value=False, reason=f"lanes off the table: {', '.join(stray)}"
            )
        keyed = [
            (line, keys[-1]) for line, _ in findings if (keys := _KEY.findall(line))
        ]
        if len(keyed) != len(findings):
            line = next(line for line, _ in findings if not _KEY.search(line))
            return EvaluationReason(value=False, reason=f"no key: {line!r}")
        counted = Counter(key for _, key in keyed)
        repeated = sorted(key for key, count in counted.items() if count > 1)
        if repeated:
            return EvaluationReason(
                value=False, reason=f"repeated key: {', '.join(repeated)}"
            )
        return EvaluationReason(value=True, reason=f"{len(keyed)} keyed finding(s)")


@dataclass(repr=False)
class Matches(Evaluator[object, object, object]):
    """
    Assert every pattern matches the output.

    The shape of an output contract: `W: -N lines.`, `bet: N/10`, a result table,
    a source URL.
    """

    patterns: Sequence[str]

    def __post_init__(self) -> None:
        self.patterns = _listed(self.patterns)

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        output = str(ctx.output)
        missing = [
            pattern for pattern in self.patterns if not re.search(pattern, output)
        ]
        if missing:
            return EvaluationReason(
                value=False, reason=f"no match for {', '.join(map(repr, missing))}"
            )
        return EvaluationReason(value=True)


@dataclass(repr=False)
class NotMatches(Evaluator[object, object, object]):
    """
    Assert no pattern matches the output.

    The work a reader must not claim: running tests, editing files, proving a
    vulnerability it was told to hold back.
    """

    patterns: Sequence[str]

    def __post_init__(self) -> None:
        self.patterns = _listed(self.patterns)

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        output = str(ctx.output)
        hits = [
            match.group(0)
            for pattern in self.patterns
            if (match := re.search(pattern, output))
        ]
        if hits:
            return EvaluationReason(
                value=False, reason=f"matched {', '.join(map(repr, hits))}"
            )
        return EvaluationReason(value=True)


@dataclass(repr=False)
class MaxWords(Evaluator[object, object, object]):
    """Assert the output stays inside a word budget."""

    words: int

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        count = _words(str(ctx.output))
        return EvaluationReason(
            value=count <= self.words, reason=f"{count} words, budget={self.words}"
        )


@dataclass(repr=False)
class MaxLines(Evaluator[object, object, object]):
    """Assert the output stays inside a line budget, blank lines excluded."""

    lines: int

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        count = sum(1 for line in str(ctx.output).splitlines() if line.strip())
        return EvaluationReason(
            value=count <= self.lines, reason=f"{count} lines, budget={self.lines}"
        )


@dataclass(repr=False)
class Brevity(Evaluator[object, object, object]):
    """
    Score output length against a target, where shorter is better.

    Full marks at or under the target, then the score falls off in proportion, so
    half the words are half the score. Reports a trend instead of gating a run.
    """

    target_words: int

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        count = _words(str(ctx.output))
        return EvaluationReason(
            value=_ratio(self.target_words, count),
            reason=f"{count}/{self.target_words} words",
        )


@dataclass(repr=False)
class Speed(Evaluator[object, object, object]):
    """
    Score wall-clock time against a target, where faster is better.

    `MaxDuration` gates a run; this one tracks how much of the budget the crew burns.
    """

    target_seconds: float

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        return EvaluationReason(
            value=_ratio(self.target_seconds, ctx.duration),
            reason=f"{ctx.duration:.1f}s/{self.target_seconds}s",
        )


@dataclass(repr=False)
class NoFiller(Evaluator[object, object, object]):
    """Assert the output carries no filler, hedging, or assistant-speak."""

    phrases: Sequence[str] = _FILLER

    def __post_init__(self) -> None:
        self.phrases = _listed(self.phrases)

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        text = _normalized(str(ctx.output))
        hits = [phrase for phrase in self.phrases if phrase in text]
        if hits:
            return EvaluationReason(value=False, reason=f"filler: {', '.join(hits)}")
        return EvaluationReason(value=True)


@dataclass(repr=False)
class ForbiddenCalls(Evaluator[object, object, object]):
    """
    Assert no tool call matches a forbidden pattern.

    Patterns are regular expressions, searched case-insensitively in each call's
    JSON arguments: test runners, linters, and anything that mutates the repository.
    Keep them tight, since a legitimate search for the same word would trip them.
    """

    patterns: Sequence[str]

    def __post_init__(self) -> None:
        self.patterns = _listed(self.patterns)

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        calls = _tool_calls(ctx)
        if calls is None:
            return EvaluationReason(value=False, reason=_NO_SPANS)
        hits = [
            f"{call.name}: {_argument_text(call.arguments)}"
            for call in calls
            if any(
                re.search(pattern, call.arguments or "", re.IGNORECASE)
                for pattern in self.patterns
            )
        ]
        if hits:
            return EvaluationReason(value=False, reason="; ".join(hits))
        return EvaluationReason(value=True)


@dataclass(repr=False)
class NoRepeatCalls(Evaluator[object, object, object]):
    """
    Assert no tool call repeats its exact arguments more than allowed.

    Reading the same file three times is wasted time no call budget catches.
    """

    max_repeats: int = 1

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        calls = _tool_calls(ctx)
        if calls is None:
            return EvaluationReason(value=False, reason=_NO_SPANS)
        counts = Counter((call.name, call.arguments or "") for call in calls)
        worst = max(counts.values(), default=0)
        if worst <= self.max_repeats:
            return EvaluationReason(value=True)
        name, arguments = next(key for key, count in counts.items() if count == worst)
        return EvaluationReason(
            value=False,
            reason=f"{name} x{worst} > {self.max_repeats}: {_argument_text(arguments)}",
        )


@dataclass(repr=False)
class MinCalls(Evaluator[object, object, object]):
    """
    Assert the run used its tools at least a minimum number of times.

    A review that read nothing is an opinion, not a review.
    """

    min_calls: int

    def evaluate(
        self, ctx: EvaluatorContext[object, object, object]
    ) -> EvaluationReason:
        calls = _tool_calls(ctx)
        if calls is None:
            return EvaluationReason(value=False, reason=_NO_SPANS)
        return EvaluationReason(
            value=len(calls) >= self.min_calls,
            reason=f"{len(calls)} tool call(s), min={self.min_calls}",
        )


RULES = (
    Brevity,
    FindingContract,
    ForbiddenCalls,
    MaxLines,
    MaxWords,
    Matches,
    MinCalls,
    NoFiller,
    NoRepeatCalls,
    NotMatches,
    PromptContract,
    Speed,
)
"""Every rule the cases may use."""
