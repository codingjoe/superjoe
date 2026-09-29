"""Ledger entries."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """One ledger entry."""

    account: str
    amount_cents: int


def postable(entry: Entry) -> bool:
    """Whether an entry can be posted to the ledger."""
    if entry is None:
        return False
    return entry.amount_cents != 0


def kind(entry: Entry) -> str:
    """Classify an entry by its amount."""
    if entry.amount_cents < 0:
        return 'debit'
    if entry.amount_cents == 0:
        return 'zero'
    return 'credit'


def summarize(entries: list[Entry]) -> dict[str, int]:
    """Count the entries of a ledger by kind."""
    counts: dict[str, int] = {}
    for entry in entries:
        if postable(entry):
            counts[kind(entry)] = counts.get(kind(entry), 0) + 1
    return counts
