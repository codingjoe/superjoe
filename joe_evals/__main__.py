from __future__ import annotations

import os
from pathlib import Path

import click

from .agents import ModelConfig, build_model, load_agents
from .container import WORKSPACE, ensure_image, in_container, launch
from .evaluators import EVALUATORS, with_judge
from .sandbox import CaseDataset, CaseRunner
from .scoring import RunReport, changed, rate, regressions, render_comment

ROOT = Path(os.environ.get("JOE_EVALS_ROOT") or Path(__file__).resolve().parent.parent)

AGENTS_DIR = ROOT / "agents"
CASES_PATH = ROOT / "cases.yaml"
FIXTURES_DIR = ROOT / "fixtures"
BASELINE_PATH = ROOT / "baseline.json"
MODELS_PATH = ROOT / "models.yaml"

MAX_CONCURRENCY = 4


def workspace_path(path: Path) -> str:
    """Return the in-container path of `path`, which must live under the repo root."""
    root, resolved = ROOT.resolve(), path.resolve()
    if not resolved.is_relative_to(root):
        raise click.UsageError(f"{path} is outside {root}, the only tree mounted")
    return str(Path(WORKSPACE) / resolved.relative_to(root))


def container_args(
    model: str | None, judge: str | None, repeats: int, out: Path
) -> list[str]:
    """Return the container command line for the host's own options."""
    args = ["run", "--repeats", str(repeats), "--out", workspace_path(out)]
    for option, value in (("--model", model), ("--judge", judge)):
        if value is not None:
            args += [option, value]
    return args


@click.group()
def main() -> None:
    """Score the superjoe crew on contract, cohesion, speed and reliability."""


@main.command()
def build() -> None:
    """Build the eval image."""
    click.echo(ensure_image(ROOT, force=True))


@main.command()
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
def run(model: str | None, judge: str | None, repeats: int, out: Path) -> None:
    """Run every case and write the score artifact."""
    if not (os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_BASE_URL")):
        raise click.UsageError(
            "set OLLAMA_API_KEY for Ollama Cloud, or OLLAMA_BASE_URL for a local Ollama"
        )
    if not in_container():
        ensure_image(ROOT)
        raise SystemExit(launch(ROOT, container_args(model, judge, repeats, out)))
    config = ModelConfig.read(MODELS_PATH)
    dataset = CaseDataset.from_file(CASES_PATH, custom_evaluator_types=EVALUATORS)
    judge_model = build_model(judge or config.judge_model)
    for case in dataset.cases:
        case.evaluators = with_judge(case.evaluators, judge_model)
    runner = CaseRunner(
        agents=load_agents(AGENTS_DIR),
        model_name=model or config.default_model,
        fixtures=FIXTURES_DIR,
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
    """Refresh the baseline from a score artifact."""
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
