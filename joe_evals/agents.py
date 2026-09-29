"""The agents under test: their markdown spec, the model plumbing and their tools."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

DEFAULT_MODEL = 'deepseek-v4.1-flash'
"""Model the suite runs and judges with, unless `models.yaml` says otherwise."""

DEFAULT_OLLAMA_URL = 'https://ollama.com'
"""Ollama Cloud endpoint, unless `OLLAMA_BASE_URL` says otherwise."""


def ollama_base_url(endpoint: str) -> str:
    """The OpenAI-compatible root the provider posts to, `/v1` included.

    The SDK builds `<base_url>/chat/completions`: `https://ollama.com` and `http://localhost:11434`
    both need the `/v1` their daemon root does not carry, and an endpoint that already names `/v1`
    keeps it.
    """
    root = endpoint.rstrip('/')
    return root if root.endswith('/v1') else f'{root}/v1'


@dataclass(frozen=True)
class AgentSpec:
    """One `agents/*.md` file: frontmatter plus the markdown body as instructions.

    Attributes:
        tools: Sandbox tools the agent may call; `None` means every tool the sandbox has.
    """

    name: str
    description: str
    instructions: str
    tools: tuple[str, ...] | None = None

    @classmethod
    def read(cls, path: Path) -> AgentSpec:
        """Read one agent file.

        Raises:
            ValueError: When the file has no frontmatter block.
        """
        _, frontmatter, instructions = path.read_text(encoding='utf-8').split('---', 2)
        data = yaml.safe_load(frontmatter)
        return cls(
            name=data['name'],
            description=data['description'],
            instructions=instructions.strip(),
            # An omitted key means every sandbox tool; an explicit empty list means no tool at all.
            tools=tuple(data['tools']) if data.get('tools') is not None else None,
        )


def load_agents(directory: Path) -> dict[str, AgentSpec]:
    """Every agent file in a directory, keyed by its frontmatter name."""
    return {spec.name: spec for spec in map(AgentSpec.read, sorted(directory.glob('*.md')))}


@dataclass(frozen=True)
class ModelConfig:
    """`models.yaml`: which Ollama models the suite runs and judges with."""

    default_model: str = DEFAULT_MODEL
    judge_model: str = DEFAULT_MODEL
    sweep: tuple[str, ...] = ()

    @classmethod
    def read(cls, path: Path) -> ModelConfig:
        """Read `models.yaml`; the judge falls back to the default model."""
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        data.setdefault('judge_model', data.get('default_model', DEFAULT_MODEL))
        return cls(**data | {'sweep': tuple(data.get('sweep', ()))})


def build_model(model_name: str) -> Model:
    """Build the Ollama model behind `model_name`.

    The endpoint comes from `OLLAMA_BASE_URL`, the API key from `OLLAMA_API_KEY`; the endpoint may
    name the daemon root or its `/v1` form, and `ollama_base_url` settles both. A local Ollama
    needs no key, so the provider fills in a placeholder. The Ollama profile answers in tool
    calls, not `json_schema`, which Cloud accepts but does not enforce.
    """
    endpoint = os.environ.get('OLLAMA_BASE_URL') or DEFAULT_OLLAMA_URL
    return OllamaModel(model_name, provider=OllamaProvider(base_url=ollama_base_url(endpoint)))
