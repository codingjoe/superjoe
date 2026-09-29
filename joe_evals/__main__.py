from __future__ import annotations

import os
from pathlib import Path

import click

from .agents import ModelConfig, build_model, load_agents
from .evaluators import EVALUATORS, with_judge
from .sandbox import CaseDataset, CaseRunner
from .scoring import RunReport, changed, rate, regressions, render_comment

ROOT = Path(os.environ.get("JOE_EVALS_ROOT") or Path(__file__).resolve().parent.parent)

AGENTS_DIR = ROOT / "agents"
CASES_DIR = ROOT / "cases"
FIXTURES_DIR = ROOT / "fixtures"
BASELINE_PATH = ROOT / "baseline.json"
MODELS_PATH = ROOT / "models.yaml"

MAX_CONCURRENCY = 4

CONTAINER_MARKER = "JOE_EVALS_CONTAINER"

CONTAINER_COMMAND = (
    'docker run --rm -v "$PWD:/work" -w /work -e OLLAMA_API_KEY joe-evals run'
)


def require_container() -> None:
    """Refuse to run the agents anywhere but inside the eval container."""
    if os.environ.get(CONTAINER_MARKER) != "1":
        raise click.UsageError(
            "the agents run their own shell, so run the suite in the container: "
            f"docker build -t joe-evals . && {CONTAINER_COMMAND}"
        )


@click.group()
def main() -> None:
    """Score the superjoe crew on contract, cohesion, speed and reliability."""


@main.command()
@click.option(
    "--agents", type=click.Path(path_type=Path), default=AGENTS_DIR, show_default=True
)
@click.option(
    "--cases", type=click.Path(path_type=Path), default=CASES_DIR, show_default=True
)
@click.option(
    "--fixtures",
    type=click.Path(path_type=Path),
    default=FIXTURES_DIR,
    show_default=True,
)
@click.option(
    "--models",
    "models_path",
    type=click.Path(path_type=Path),
    default=MODELS_PATH,
    show_default=True,
)
@click.option(
    "--model",
    default=None,
    help="Model to run the agents with; defaults to models.yaml.",
)
@click.option(
    "--judge", default=None, help="Model that scores cohesion; defaults to models.yaml."
)
@click.option(
    "--repeats", type=int, default=1, show_default=True, help="Runs per case."
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("evals-report.json"),
    show_default=True,
)
def run(
    agents: Path,
    cases: Path,
    fixtures: Path,
    models_path: Path,
    model: str | None,
    judge: str | None,
    repeats: int,
    out: Path,
) -> None:
    """Run every case and write the score artifact."""
    require_container()
    if not (os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_BASE_URL")):
        raise click.UsageError(
            "set OLLAMA_API_KEY for Ollama Cloud, or OLLAMA_BASE_URL for a local Ollama"
        )
    paths = sorted(cases.rglob("*.yaml"))
    if not paths:
        raise click.UsageError(f"no case files under {cases}")
    config = ModelConfig.read(models_path)
    dataset = CaseDataset.read(paths, EVALUATORS)
    judge_model = build_model(judge or config.judge_model)
    for case in dataset.cases:
        case.evaluators = with_judge(case.evaluators, judge_model)
    runner = CaseRunner(
        agents=load_agents(agents),
        model_name=model or config.default_model,
        fixtures=fixtures,
    )
    runner.validate(dataset.cases)
    report = dataset.evaluate_sync(
        runner.run, repeat=repeats, max_concurrency=MAX_CONCURRENCY, progress=False
    )
    artifact = rate(report, model=model or config.default_model)
    artifact.save(out)
    click.echo(f"{len(artifact.cases)} case runs -> {out}")
    if reason := artifact.failure():
        raise click.ClickException(reason)


@main.command()
@click.option("--report", type=click.Path(path_type=Path, exists=True), required=True)
@click.option(
    "--out", type=click.Path(path_type=Path), default=BASELINE_PATH, show_default=True
)
def baseline(report: Path, out: Path) -> None:
    """Refresh the committed baseline from a score artifact."""
    RunReport.read(report).summary().save(out)
    click.echo(f"baseline -> {out}")


@main.command()
@click.option("--report", type=click.Path(path_type=Path, exists=True), required=True)
@click.option(
    "--baseline",
    "baseline_path",
    type=click.Path(path_type=Path, exists=True),
    default=BASELINE_PATH,
    show_default=True,
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the comment to this file.",
)
def comment(report: Path, baseline_path: Path, out: Path | None) -> None:
    """Print the PR comment for a score artifact."""
    before, current = RunReport.read(baseline_path), RunReport.read(report)
    body = render_comment(before, current)
    broken = regressions(before, current)
    if out is None:
        click.echo(body)
    elif changed(before, current):
        out.write_text(body, encoding="utf-8")
        click.echo(f"comment -> {out}")
    else:
        click.echo("no rating changed, no comment written")
    if broken:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
