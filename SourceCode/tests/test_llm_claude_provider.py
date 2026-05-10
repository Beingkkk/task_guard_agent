"""Tests for ClaudeProvider.

Relates-to: FR-3
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from taskguard.llm.base import LLMError, Message, ToolDefinition
from taskguard.llm.claude_provider import ClaudeProvider


def _load_claude_config() -> dict[str, str]:
    """Read config-claude.json for base_url and model (tests use mock key)."""
    path = Path("config/config-claude.json")
    if path.exists():
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        return {
            "base_url": cfg.get("llm_base_url") or "https://api.anthropic.com",
            "model": cfg.get("model_name") or "claude-sonnet-4-6",
        }
    return {"base_url": "https://api.anthropic.com", "model": "claude-sonnet-4-6"}


@pytest.mark.asyncio
async def test_complete_calls_messages_create() -> None:
    mock_response = mock.MagicMock()
    mock_response.content = []
    mock_response.usage = mock.MagicMock(input_tokens=10, output_tokens=5)

    cfg = _load_claude_config()
    with mock.patch("anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = mock_response

        provider = ClaudeProvider(api_key="test-key", model=cfg["model"], base_url=cfg["base_url"])
        msg = Message(role="user", content="hello")
        result = await provider.complete(system="sys", messages=[msg])

        instance.messages.create.assert_called_once()
        call_kwargs = instance.messages.create.call_args.kwargs
        assert call_kwargs["model"] == cfg["model"]
        assert call_kwargs["system"] == "sys"
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"
        assert call_kwargs["messages"][0]["content"] == "hello"
        assert result.content == ""


@pytest.mark.asyncio
async def test_complete_with_tool_calls() -> None:
    mock_tool_use = mock.MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.id = "call_1"
    mock_tool_use.name = "progress_extract"
    mock_tool_use.input = {"percentage": 75.0}

    mock_response = mock.MagicMock()
    mock_response.content = [mock_tool_use]
    mock_response.usage = mock.MagicMock(input_tokens=100, output_tokens=50)

    cfg = _load_claude_config()
    with mock.patch("anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = mock_response

        provider = ClaudeProvider(api_key="test-key", model=cfg["model"], base_url=cfg["base_url"])
        tool = ToolDefinition(
            name="progress_extract",
            description="extract",
            input_schema={"type": "object"},
        )
        msg = Message(role="user", content="log lines")
        result = await provider.complete(system=None, messages=[msg], tools=[tool])

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_1"
        assert result.tool_calls[0].name == "progress_extract"
        assert result.tool_calls[0].arguments == b'{"percentage": 75.0}'
        assert result.usage is not None
        assert result.usage.input_tokens == 100


@pytest.mark.asyncio
async def test_complete_api_error_raises_llm_error() -> None:
    cfg = _load_claude_config()
    with mock.patch("anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.side_effect = Exception("API error")

        provider = ClaudeProvider(api_key="test-key", model=cfg["model"], base_url=cfg["base_url"])
        msg = Message(role="user", content="hello")
        with pytest.raises(LLMError):
            await provider.complete(system=None, messages=[msg])


@pytest.mark.asyncio
async def test_complete_empty_response() -> None:
    mock_response = mock.MagicMock()
    mock_response.content = []
    mock_response.usage = None

    cfg = _load_claude_config()
    with mock.patch("anthropic.Anthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create.return_value = mock_response

        provider = ClaudeProvider(api_key="test-key", model=cfg["model"], base_url=cfg["base_url"])
        msg = Message(role="user", content="hello")
        result = await provider.complete(system=None, messages=[msg])

        assert result.content == ""
        assert result.tool_calls == []
