"""Tests for IntentParser.

Relates-to: FR-4
"""

import json

import pytest

from taskguard.interaction.intent_parser import IntentParser
from taskguard.llm.base import BaseProvider, LLMResponse, Message, Usage


class FakeProvider(BaseProvider):
    """Mock provider that returns a fixed JSON response."""

    def __init__(self, response_json: str) -> None:
        self._response = response_json

    async def complete(
        self,
        system: str | None,
        messages: list[Message],
        tools: list | None = None,
    ) -> LLMResponse:
        return LLMResponse(content=self._response, usage=Usage(50, 30))


class FailingProvider(BaseProvider):
    """Mock provider that always raises."""

    async def complete(
        self,
        system: str | None,
        messages: list[Message],
        tools: list | None = None,
    ) -> LLMResponse:
        from taskguard.llm.base import LLMError

        raise LLMError("api down")


class TestIntentParser:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        response = json.dumps(
            {
                "tool_name": "watch_task",
                "params": {"alias": "下载B", "log": "file://C:\\data\\dl.log"},
                "missing_params": [],
                "confidence": 0.95,
            }
        )
        parser = IntentParser(FakeProvider(response))
        result = await parser.parse("帮我监控下载B，日志在 C:\\data\\dl.log")
        assert result.tool_name == "watch_task"
        assert result.params["alias"] == "下载B"
        assert result.params["log"] == "file://C:\\data\\dl.log"
        assert result.confidence == 0.95
        assert result.missing_params == []

    @pytest.mark.asyncio
    async def test_missing_params(self) -> None:
        response = json.dumps(
            {
                "tool_name": "watch_task",
                "params": {},
                "missing_params": ["alias", "log"],
                "confidence": 0.8,
            }
        )
        parser = IntentParser(FakeProvider(response))
        result = await parser.parse("帮我监控一个下载任务")
        assert result.missing_params == ["alias", "log"]

    @pytest.mark.asyncio
    async def test_unknown_intent(self) -> None:
        response = json.dumps(
            {
                "tool_name": "unknown",
                "params": {},
                "missing_params": [],
                "confidence": 0.1,
            }
        )
        parser = IntentParser(FakeProvider(response))
        result = await parser.parse("今天天气怎么样")
        assert result.tool_name == "unknown"

    @pytest.mark.asyncio
    async def test_provider_failure_fallback(self) -> None:
        parser = IntentParser(FailingProvider())
        result = await parser.parse("帮我监控下载A")
        assert result.tool_name == "unknown"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_malformed_json_fallback(self) -> None:
        parser = IntentParser(FakeProvider("not-json"))
        result = await parser.parse("帮我监控下载A")
        assert result.tool_name == "unknown"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_system_prompt_contains_tools(self) -> None:
        captured_system: str | None = None

        class CapturingProvider(BaseProvider):
            async def complete(
                self,
                system: str | None,
                messages: list[Message],
                tools: list | None = None,
            ) -> LLMResponse:
                nonlocal captured_system
                captured_system = system
                return LLMResponse(
                    content='{"tool_name":"unknown","params":{},"missing_params":[],"confidence":0.0}',
                    usage=Usage(10, 5),
                )

        parser = IntentParser(CapturingProvider())
        await parser.parse("test")
        assert captured_system is not None
        assert "watch_task" in captured_system
        assert "unwatch_task" in captured_system

    @pytest.mark.asyncio
    async def test_provider_none(self) -> None:
        parser = IntentParser(None)
        result = await parser.parse("帮我监控下载A")
        assert result.tool_name == "unknown"
        assert result.confidence == 0.0
