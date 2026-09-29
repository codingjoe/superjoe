import os
import sys
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_tracer_provider, set_tracer_provider
from pydantic_evals.evaluators.llm_as_a_judge import set_default_judge_model

from .agents import DEFAULT_MODEL, build_model, load_agents
from .cases import CaseDataset, CaseRunner
from .container import build_image, in_container, launch

ROOT = Path(os.environ.get("JOE_EVALS_ROOT") or Path(__file__).resolve().parent.parent)

AGENTS_DIR = ROOT / "agents"
CASES_PATH = ROOT / "cases.yaml"
FIXTURES_DIR = ROOT / "fixtures"

MAX_CONCURRENCY = 4


def model_settings() -> tuple[str, str, int]:
    model = os.environ.get("JOE_EVALS_MODEL") or DEFAULT_MODEL
    return (
        model,
        os.environ.get("JOE_EVALS_JUDGE") or model,
        int(os.environ.get("JOE_EVALS_REPEATS") or 1),
    )


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
    dataset = CaseDataset.from_file(CASES_PATH)
    set_default_judge_model(build_model(judge))
    runner = CaseRunner(
        agents=load_agents(AGENTS_DIR), model_name=model, fixtures=FIXTURES_DIR
    )
    runner.validate(dataset.cases)
    report = dataset.evaluate_sync(
        runner.run, repeat=repeats, max_concurrency=MAX_CONCURRENCY, progress=False
    )
    report.print(width=200, include_output=False, include_reasons=True)
    for failure in report.failures:
        sys.stdout.write(f"{failure.name}: {failure.error_message}\n")
    if report.failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
