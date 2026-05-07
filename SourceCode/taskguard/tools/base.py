"""Tool Registry and base tool abstraction.

Relates-to: FR-1
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ToolResult:
    """Uniform return container for all tools."""

    ok: bool
    data: Any | None = None
    error_code: str | None = None
    message: str = ""


class BaseTool(ABC):
    """Abstract base for all TaskGuard tools."""

    name: str = ""
    description: str = ""
    params_schema: dict[str, Any] | None = None

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute the tool with given parameters."""
        ...


class ToolRegistry:
    """Central registry for tools."""

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool) -> None:
        """Register a tool instance."""
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> BaseTool:
        """Retrieve a tool by name."""
        if name not in cls._tools:
            raise KeyError(f"Tool '{name}' not registered")
        return cls._tools[name]

    @classmethod
    def list_all(cls) -> list[BaseTool]:
        """Return all registered tools."""
        return list(cls._tools.values())

    @classmethod
    def clear(cls) -> None:
        """Remove all tools (useful for testing)."""
        cls._tools.clear()
