import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import get_tracer_provider, set_tracer_provider
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_evals import Dataset
from pydantic_evals.evaluators.llm_as_a_judge import set_default_judge_model
from pydantic_evals.reporting import EvaluationReport

from .agents import DEFAULT_MODEL, AgentSpec, build_agent, build_model
from .container import build_image, in_container, launch

ROOT = Path(os.environ.get("JOE_EVALS_ROOT") or Path(__file__).resolve().parent.parent)

AGENTS_DIR = ROOT / "agents"
CASES_DIR = ROOT / "cases"

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


def task(agent: Agent[None, str]) -> Callable[[str], str]:
    def run(prompt: str) -> str:
        return agent.run_sync(prompt).output

    return run


def evaluate(path: Path, model: Model, repeats: int) -> EvaluationReport[str, str, Any]:
    dataset = Dataset[str, str, Any].from_file(path)
    agent = build_agent(AgentSpec.read(AGENTS_DIR / f"{path.stem}.md"), model, ROOT)
    return dataset.evaluate_sync(
        task(agent), repeat=repeats, max_concurrency=MAX_CONCURRENCY, progress=False
    )


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
    model_name, judge_name, repeats = model_settings()
    set_default_judge_model(build_model(judge_name))
    model = build_model(model_name)
    reports = [
        evaluate(path, model, repeats) for path in sorted(CASES_DIR.glob("*.yaml"))
    ]
    for report in reports:
        report.print(width=100, include_output=False, include_reasons=True)
        for failure in report.failures:
            sys.stdout.write(f"{failure.name}: {failure.error_message}\n")
    if any(report.failures for report in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
