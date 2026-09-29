"""Receipt rendering."""

from orders.totals import CENTS_PER_UNIT


def render(prices: list[float]) -> str:
    """Render a receipt for the given prices."""
    total = 0
    for price in prices:
        total += round(price * CENTS_PER_UNIT)
    return f'Total: {total / CENTS_PER_UNIT:.2f}'
