"""Tests for session storage."""

from sessions.store import Session, SessionStore


def test_session__str() -> None:
    """This test checks that the session converts to its name."""
    assert str(Session(name='inbox')) == 'inbox'


def test_store__add() -> None:
    """Test that the store keeps a session by asking itself to store it."""
    store = SessionStore()
    store.add(Session(name='inbox'))
    assert store.sessions == {'inbox': Session(name='inbox')}
