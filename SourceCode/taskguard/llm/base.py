"""Provider abstraction layer for LLM backends.

Relates-to: FR-3
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Message:
    """A unified message format across providers."""

    role: Literal["system", "user", "assistant"]
    content: str
    tool_calls: list["ToolCall"] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class ToolCall:
    """A tool invocation from the model."""

    id: str
    name: str
    arguments: bytes  # JSON bytes


@dataclass
class ToolDefinition:
    """Schema definition for a tool exposed to the model."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class Usage:
    """Token usage statistics."""

    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    """Normalized response from any provider."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    finish_reason: str | None = None


class LLMError(Exception):
    """Raised when an LLM provider call fails."""


class BaseProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def complete(
        self,
        system: str | None,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        """Send messages to the LLM and return a normalized response."""
        ...


__all__ = [
    "BaseProvider",
    "LLMError",
    "LLMResponse",
    "Message",
    "ToolCall",
    "ToolDefinition",
    "Usage",
]
