"""Tests for OpenAIProvider.

Relates-to: FR-3
"""

import json
from pathlib import Path
from unittest import mock

import httpx
import pytest

from taskguard.llm.base import LLMError, Message, ToolDefinition, Usage
from taskguard.llm.openai_provider import OpenAIProvider


def _load_openai_config() -> dict[str, str]:
    """Read config-openai.json for base_url and model (tests use mock key)."""
    path = Path("config/config-openai.json")
    if path.exists():
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        return {
            "base_url": cfg.get("llm_base_url", "https://api.openai.com"),
            "model": cfg.get("model_name") or "kimi-k2.6",
        }
    return {"base_url": "https://api.openai.com", "model": "kimi-k2.6"}


@pytest.fixture
def provider() -> OpenAIProvider:
    cfg = _load_openai_config()
    return OpenAIProvider(
        api_key="test-key",
        model=cfg["model"],
        base_url=cfg["base_url"],
    )


@pytest.mark.asyncio
async def test_complete_payload_format(provider: OpenAIProvider) -> None:
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "hello",
                    "tool_calls": None,
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    with mock.patch("httpx.AsyncClient.post", return_value=mock_response):
        msg = Message(role="user", content="test")
        result = await provider.complete(system="sys", messages=[msg])

        call_args = httpx.AsyncClient.post.call_args
        assert call_args is not None
        payload = call_args.kwargs["json"]
        assert payload["model"] == provider._model
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "sys"
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "test"
        assert result.content == "hello"
        assert result.usage == Usage(10, 5)


@pytest.mark.asyncio
async def test_complete_with_tool_calls(provider: OpenAIProvider) -> None:
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "progress_extract",
                                "arguments": '{"percentage": 75.0}',
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }

    with mock.patch("httpx.AsyncClient.post", return_value=mock_response):
        tool = ToolDefinition(
            name="progress_extract",
            description="extract",
            input_schema={"type": "object"},
        )
        msg = Message(role="user", content="log lines")
        result = await provider.complete(system=None, messages=[msg], tools=[tool])

        call_args = httpx.AsyncClient.post.call_args
        payload = call_args.kwargs["json"]
        assert "tools" in payload
        assert payload["tools"][0]["type"] == "function"
        assert payload["tools"][0]["function"]["name"] == "progress_extract"

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_1"
        assert result.tool_calls[0].name == "progress_extract"
        assert result.tool_calls[0].arguments == b'{"percentage": 75.0}'
        assert result.usage == Usage(100, 50)


@pytest.mark.asyncio
async def test_complete_http_500_raises_llm_error(provider: OpenAIProvider) -> None:
    mock_response = mock.MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with mock.patch("httpx.AsyncClient.post", return_value=mock_response):
        msg = Message(role="user", content="hello")
        with pytest.raises(LLMError):
            await provider.complete(system=None, messages=[msg])


@pytest.mark.asyncio
async def test_complete_timeout_raises_llm_error(provider: OpenAIProvider) -> None:
    with mock.patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.TimeoutException("timeout"),
    ):
        msg = Message(role="user", content="hello")
        with pytest.raises(LLMError):
            await provider.complete(system=None, messages=[msg])


@pytest.mark.asyncio
async def test_complete_non_json_response_raises_llm_error(
    provider: OpenAIProvider,
) -> None:
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("not json")
    mock_response.text = "not json"

    with mock.patch("httpx.AsyncClient.post", return_value=mock_response):
        msg = Message(role="user", content="hello")
        with pytest.raises(LLMError):
            await provider.complete(system=None, messages=[msg])
