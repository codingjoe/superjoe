from pathlib import Path

REQUIRED = {
    "superjoe-code": (
        "## Human review",
        "`superjoe-code` ends after the final `killJoe` sweep.",
        "Start `superjoe-ship` only on the user's next request.",
    ),
    "superjoe-ship": (
        "Run it after the user has reviewed",
        "`testJoe` writes tests",
        "Run `docuJoe` after the testing loop is green.",
    ),
}

FORBIDDEN_IN_CODE = ("## The testing loop", "## Modes", "## Ultra", "Mode:")

REQUIRED_IN_CONTRACT = (
    "## Two skills",
    "`superjoe-ship` adds tests and docs after the review.",
)


def check_skills(root: Path) -> list[str]:
    """Check the split skills keep their contract without running a model."""
    failures: list[str] = []
    for name, needles in REQUIRED.items():
        text = (root / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        failures.extend(
            f"{name}: missing {needle!r}" for needle in needles if needle not in text
        )
    code = (root / "skills/superjoe-code/SKILL.md").read_text(encoding="utf-8")
    failures.extend(
        f"superjoe-code: must not contain {needle!r}"
        for needle in FORBIDDEN_IN_CODE
        if needle in code
    )
    contract = (root / "skills/superjoe-code/CONTRACT.md").read_text(encoding="utf-8")
    failures.extend(
        f"contract: missing {needle!r}"
        for needle in REQUIRED_IN_CONTRACT
        if needle not in contract
    )
    return failures
