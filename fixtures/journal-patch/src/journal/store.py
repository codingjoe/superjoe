"""Journal storage."""

from dataclasses import dataclass, field


@dataclass
class Journal:
    """A journal of amounts."""

    amounts: list[int] = field(default_factory=list)

    def add(self, amount_cents: int) -> None:
        """Append an amount to the journal."""
        self.amounts.append(amount_cents)
