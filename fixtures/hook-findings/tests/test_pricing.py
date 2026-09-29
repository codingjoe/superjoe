"""Tests for price formatting."""

from pricing import format_cents


def test_format_cents__rounds_half_up() -> None:
    """Round a half cent up."""
    assert format_cents(1235) == '12.36'
