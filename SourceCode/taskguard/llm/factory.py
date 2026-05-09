"""Provider factory.

Relates-to: FR-3
"""

from dataclasses import dataclass

from taskguard.llm.base import BaseProvider
from taskguard.llm.claude_provider import ClaudeProvider
from taskguard.llm.openai_provider import OpenAIProvider


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    provider: str
    model: str
    api_key: str
    base_url: str | None = None


def create_provider(config: LLMConfig) -> BaseProvider:
    """Create a provider instance from configuration."""
    if config.provider == "claude":
        return ClaudeProvider(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
        )
    if config.provider == "openai":
        return OpenAIProvider(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url or "https://api.openai.com",
        )
    raise ValueError(f"Unknown provider: {config.provider}")
