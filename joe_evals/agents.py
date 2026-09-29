import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai_harness import Coder, Researcher

DEFAULT_MODEL = "deepseek-v4.1-flash"

DEFAULT_OLLAMA_URL = "https://ollama.com"


def ollama_base_url(endpoint: str) -> str:
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


def build_model(model_name: str) -> Model:
    endpoint = os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL
    return OllamaModel(
        model_name, provider=OllamaProvider(base_url=ollama_base_url(endpoint))
    )


def build_agent(spec: AgentSpec, model: Model, root: Path) -> Agent[None, str]:
    capabilities: list[AbstractCapability[None]] = [Coder(root)]
    if "WebSearch" in (spec.tools or ()):
        capabilities.append(Researcher())
    agent = Agent(
        model,
        name=spec.name,
        description=spec.description,
        instructions=spec.instructions,
        capabilities=capabilities,
    )
    agent.instrument = True
    return agent
