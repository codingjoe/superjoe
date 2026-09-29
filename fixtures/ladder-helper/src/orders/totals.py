"""Order totals."""

from collections.abc import Iterable

CENTS_PER_UNIT = 100


def sum_cents(prices: Iterable[float]) -> int:
    """Sum prices in cents."""
    return sum(round(price * CENTS_PER_UNIT) for price in prices)
