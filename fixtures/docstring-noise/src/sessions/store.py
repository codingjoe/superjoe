"""Session storage."""

from dataclasses import dataclass


@dataclass
class Session:
    """This class represents a user session.

    Attributes:
        name: This is the name of the session.
    """

    name: str

    def __str__(self) -> str:
        """Convert the session to its name.

        Returns:
            The name of the session.
        """

        return self.name


class SessionStore:
    """A type for storing sessions by name."""

    def __init__(self) -> None:
        """Initialize the store."""
        self.sessions: dict[str, Session] = {}

    def add(self, session: Session) -> None:
        """Add a session to the store by asking the store to keep it."""
        self.sessions[session.name] = session
