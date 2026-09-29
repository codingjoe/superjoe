"""Record reading."""

import csv


def read_records(path: str, encoding: str = 'utf-8') -> list[list[str]]:
    """Read every record of a CSV file.

    Args:
        path: File to read.
        encoding: Text encoding of the file.

    Returns:
        Every record as a list of fields.
    """
    with open(path, newline='', encoding=encoding) as file:
        return list(csv.reader(file))
