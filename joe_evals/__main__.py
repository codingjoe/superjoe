import os
import sys
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_tracer_provider, set_tracer_provider

from .agents import DEFAULT_MODEL, build_model, load_agents
from .container import build_image, in_container, launch
from .evaluators import EVALUATORS, with_judge
from .sandbox import CaseDataset, CaseRunner
from .scoring import RunReport, changed, rate, regressions, render_comment

ROOT = Path(os.environ.get("JOE_EVALS_ROOT") or Path(__file__).resolve().parent.parent)

AGENTS_DIR = ROOT / "agents"
CASES_PATH = ROOT / "cases.yaml"
FIXTURES_DIR = ROOT / "fixtures"

MAX_CONCURRENCY = 4


def artifact(name: str, default: str) -> Path:
    return ROOT / (os.environ.get(name) or default)


REPORT = artifact("JOE_EVALS_REPORT", "evals-report.json")
BASELINE = artifact("JOE_EVALS_BASELINE", "baseline.json")
COMMENT = artifact("JOE_EVALS_COMMENT", "comment.md")


def model_settings() -> tuple[str, str, int]:
    model = os.environ.get("JOE_EVALS_MODEL") or DEFAULT_MODEL
    return (
        model,
        os.environ.get("JOE_EVALS_JUDGE") or model,
        int(os.environ.get("JOE_EVALS_REPEATS") or 1),
    )


def baseline_report(model: str) -> RunReport | None:
    if not BASELINE.exists():
        return None
    before = RunReport.read(BASELINE)
    return before if before.model == model else None


def build() -> None:
    sys.stdout.write(f"{build_image(ROOT)}\n")


def main() -> None:
    if not (os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_BASE_URL")):
        sys.stderr.write(
            "set OLLAMA_API_KEY for Ollama Cloud, or OLLAMA_BASE_URL for a local Ollama\n"
        )
        raise SystemExit(1)
    if not in_container():
        raise SystemExit(launch(ROOT))
    if not isinstance(get_tracer_provider(), TracerProvider):
        set_tracer_provider(TracerProvider())
    model, judge, repeats = model_settings()
    before = baseline_report(model)
    dataset = CaseDataset.from_file(CASES_PATH, custom_evaluator_types=EVALUATORS)
    judge_model = build_model(judge)
    for case in dataset.cases:
        case.evaluators = with_judge(case.evaluators, judge_model)
    runner = CaseRunner(
        agents=load_agents(AGENTS_DIR), model_name=model, fixtures=FIXTURES_DIR
    )
    runner.validate(dataset.cases)
    report = dataset.evaluate_sync(
        runner.run, repeat=repeats, max_concurrency=MAX_CONCURRENCY, progress=False
    )
    scored = rate(report, model=model)
    scored.save(REPORT)
    sys.stdout.write(f"{len(scored.cases)} case runs -> {REPORT}\n")
    broken: list[str] = []
    if before is not None:
        if changed(before, scored):
            COMMENT.write_text(render_comment(before, scored), encoding="utf-8")
            sys.stdout.write(f"comment -> {COMMENT}\n")
        broken = [delta.case for delta in regressions(before, scored)]
    if reason := scored.failure():
        sys.stderr.write(f"{reason}\n")
        raise SystemExit(1)
    if broken:
        sys.stderr.write(f"regressions: {', '.join(broken)}\n")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
