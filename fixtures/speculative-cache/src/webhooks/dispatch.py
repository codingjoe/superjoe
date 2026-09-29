"""Webhook dispatch."""

from collections.abc import Callable

Handler = Callable[[dict[str, object]], None]

HANDLERS: dict[str, Handler] = {}


def register(event: str, handler: Handler) -> None:
    """Register the handler for an event."""
    HANDLERS[event] = handler


def dispatch(event: str, payload: dict[str, object]) -> None:
    """Send a payload to the handler of an event."""
    HANDLERS[event](payload)
