"""Configuration loading."""

import json
from abc import ABC, abstractmethod


class ConfigSource(ABC):
    """A place configuration comes from."""

    @abstractmethod
    def load(self) -> dict[str, str]:
        """Read the configuration."""


class EnvironmentSource(ConfigSource):
    """Configuration read from the process environment."""

    def __init__(self, environment: dict[str, str]) -> None:
        """Remember the environment mapping."""
        self.environment = environment

    def load(self) -> dict[str, str]:
        """Read the configuration."""
        return {
            key.removeprefix('APP_').lower(): value
            for key, value in self.environment.items()
            if key.startswith('APP_')
        }


def snake_case(name: str) -> str:
    """Turn a configuration name into its key."""
    result = ''
    for index, character in enumerate(name):
        if character.isupper() and index:
            result += '_'
        result += character.lower()
    return result


def get(key: str, source: ConfigSource) -> str:
    """Read one configuration value."""
    if not key:
        raise ValueError('key is required')
    try:
        return source.load()[snake_case(key)]
    except Exception:
        return ''
