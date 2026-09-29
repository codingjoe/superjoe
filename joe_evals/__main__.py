import os
from pathlib import Path

from .agents import ModelConfig, build_model, load_agents
from .container import ensure_image, in_container, launch
from .evaluators import EVALUATORS, with_judge
from .sandbox import CaseDataset, CaseRunner
from .scoring import RunReport, changed, rate, regressions, render_comment

ROOT = Path(os.environ.get("JOE_EVALS_ROOT") or Path(__file__).resolve().parent.parent)

AGENTS_DIR = ROOT / "agents"
CASES_PATH = ROOT / "cases.yaml"
FIXTURES_DIR = ROOT / "fixtures"
MODELS_PATH = ROOT / "models.yaml"

MAX_CONCURRENCY = 4


def artifact(name: str, default: str) -> Path:
    """Return the artifact path the environment names, beside the sources."""
    return ROOT / (os.environ.get(name) or default)


REPORT = artifact("JOE_EVALS_REPORT", "evals-report.json")
BASELINE = artifact("JOE_EVALS_BASELINE", "baseline.json")
COMMENT = artifact("JOE_EVALS_COMMENT", "comment.md")


def model_settings() -> tuple[str, str, int]:
    """Return the model, the judge and the repeat count this run uses."""
    config = ModelConfig.read(MODELS_PATH)
    return (
        os.environ.get("JOE_EVALS_MODEL") or config.default_model,
        os.environ.get("JOE_EVALS_JUDGE") or config.judge_model,
        int(os.environ.get("JOE_EVALS_REPEATS") or 1),
    )


def baseline_report(model: str) -> RunReport | None:
    """Return the baseline to compare against, when it scored the same model."""
    if not BASELINE.exists():
        return None
    before = RunReport.read(BASELINE)
    return before if before.model == model else None


def build() -> None:
    """Build the eval image."""
    print(ensure_image(ROOT, force=True))


def main() -> None:
    """Score the suite in the eval image and write the report and the comment."""
    if not (os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_BASE_URL")):
        raise SystemExit(
            "set OLLAMA_API_KEY for Ollama Cloud, or OLLAMA_BASE_URL for a local Ollama"
        )
    if not in_container():
        ensure_image(ROOT)
        raise SystemExit(launch(ROOT))
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
    print(f"{len(scored.cases)} case runs -> {REPORT}")
    broken: list[str] = []
    if before is not None:
        if changed(before, scored):
            COMMENT.write_text(render_comment(before, scored), encoding="utf-8")
            print(f"comment -> {COMMENT}")
        broken = [delta.case for delta in regressions(before, scored)]
    if reason := scored.failure():
        raise SystemExit(reason)
    if broken:
        raise SystemExit(f"regressions: {', '.join(broken)}")


if __name__ == "__main__":
    main()
