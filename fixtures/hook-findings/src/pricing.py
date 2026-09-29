"""Price formatting."""

import json


def format_cents(cents: int) -> str:
    """Format cents as a price."""
    return f'{cents / 100:.2f}'
