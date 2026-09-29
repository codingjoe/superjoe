"""Writing CSV exports."""

import csv


def write(path: str, rows: list[list[str]]) -> None:
    """Write rows to a CSV file."""
    with open(path, 'w', newline='', encoding='utf-8') as file:
        csv.writer(file).writerows(rows)
