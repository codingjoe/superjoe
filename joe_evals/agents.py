import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

DEFAULT_MODEL = "deepseek-v4.1-flash"

DEFAULT_OLLAMA_URL = "https://ollama.com"


def ollama_base_url(endpoint: str) -> str:
    """The OpenAI-compatible root the provider posts to, `/v1` included."""
    root = endpoint.rstrip("/")
    return root if root.endswith("/v1") else f"{root}/v1"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    instructions: str
    tools: tuple[str, ...] | None = None

    @classmethod
    def read(cls, path: Path) -> AgentSpec:
        _, frontmatter, instructions = path.read_text(encoding="utf-8").split("---", 2)
        data = yaml.safe_load(frontmatter)
        return cls(
            name=data["name"],
            description=data["description"],
            instructions=instructions.strip(),
            tools=tuple(data["tools"]) if data.get("tools") is not None else None,
        )


def load_agents(directory: Path) -> dict[str, AgentSpec]:
    return {
        spec.name: spec for spec in map(AgentSpec.read, sorted(directory.glob("*.md")))
    }


@dataclass(frozen=True)
class ModelConfig:
    default_model: str = DEFAULT_MODEL
    judge_model: str = DEFAULT_MODEL
    sweep: tuple[str, ...] = ()

    @classmethod
    def read(cls, path: Path) -> ModelConfig:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data.setdefault("judge_model", data.get("default_model", DEFAULT_MODEL))
        return cls(**data | {"sweep": tuple(data.get("sweep", ()))})


def build_model(model_name: str) -> Model:
    """Build the Ollama model behind `model_name`."""
    endpoint = os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL
    return OllamaModel(
        model_name, provider=OllamaProvider(base_url=ollama_base_url(endpoint))
    )
