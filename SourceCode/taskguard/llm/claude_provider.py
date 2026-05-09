"""ClaudeProvider — Anthropic Messages API implementation.

Relates-to: FR-3
"""

import asyncio
import json
from typing import Any

import anthropic

from taskguard.llm.base import (
    BaseProvider,
    LLMError,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
    Usage,
)


class ClaudeProvider(BaseProvider):
    """Provider backed by the Anthropic SDK."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url is not None:
            kwargs["base_url"] = base_url
        self._client = anthropic.Anthropic(**kwargs)
        self._model = model

    async def complete(
        self,
        system: str | None,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        anthropic_messages = [{"role": m.role, "content": m.content} for m in messages]

        anthropic_tools: list[dict[str, Any]] | None = None
        if tools:
            anthropic_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": 1024,
        }
        if system is not None:
            kwargs["system"] = system
        if anthropic_tools is not None:
            kwargs["tools"] = anthropic_tools

        try:
            response = await asyncio.to_thread(self._client.messages.create, **kwargs)  # type: ignore[arg-type]
        except anthropic.APIError as exc:
            raise LLMError(str(exc)) from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        content_text = ""
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input).encode(),
                    )
                )

        usage = None
        if response.usage is not None:
            usage = Usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            usage=usage,
        )
