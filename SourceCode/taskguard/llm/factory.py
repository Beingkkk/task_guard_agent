"""Provider factory.

Relates-to: FR-3
"""

from dataclasses import dataclass

from taskguard.llm.base import BaseProvider
from taskguard.llm.claude_provider import ClaudeProvider


@dataclass
class LLMConfig:
    """Configuration for the Claude LLM provider."""

    model: str
    api_key: str
    base_url: str | None = None


def create_provider(config: LLMConfig) -> BaseProvider:
    """Create a Claude provider instance from configuration."""
    return ClaudeProvider(
        api_key=config.api_key,
        model=config.model,
        base_url=config.base_url,
    )
