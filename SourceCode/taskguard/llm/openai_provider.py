"""OpenAIProvider — OpenAI-compatible chat.completions implementation.

Relates-to: FR-3
"""

from typing import Any

import httpx

from taskguard.llm.base import (
    BaseProvider,
    LLMError,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
    Usage,
)


class OpenAIProvider(BaseProvider):
    """Provider backed by an OpenAI-compatible HTTP endpoint."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def complete(
        self,
        system: str | None,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        openai_messages: list[dict[str, str]] = []
        if system is not None:
            openai_messages.append({"role": "system", "content": system})
        for m in messages:
            openai_messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=60.0,
                )
        except httpx.TimeoutException as exc:
            raise LLMError(f"Timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"HTTP error: {exc}") from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        if response.status_code != 200:
            raise LLMError(
                f"HTTP {response.status_code}: {response.text[:200]}",
            )

        try:
            data = response.json()
        except Exception as exc:
            raise LLMError(f"Invalid JSON response: {exc}") from exc

        choice = data["choices"][0]["message"]
        content_text = choice.get("content") or ""

        tool_calls: list[ToolCall] = []
        raw_tool_calls = choice.get("tool_calls")
        if raw_tool_calls:
            for tc in raw_tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"].encode(),
                    )
                )

        usage = None
        raw_usage = data.get("usage")
        if raw_usage is not None:
            usage = Usage(
                input_tokens=raw_usage.get("prompt_tokens", 0),
                output_tokens=raw_usage.get("completion_tokens", 0),
            )

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            usage=usage,
        )
