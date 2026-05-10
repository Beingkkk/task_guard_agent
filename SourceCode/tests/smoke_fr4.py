"""FR-4 Smoke Test.

Run: python tests/smoke_fr4.py

Relates-to: FR-4
"""

import asyncio
import json

from taskguard.interaction.intent_parser import IntentParser
from taskguard.interaction.parser import CommandParser, ParseError
from taskguard.llm.base import BaseProvider, LLMResponse, Message, Usage
from taskguard.tools.help import HelpTool
from taskguard.tools.query import QueryProgressTool


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


async def test_command_parser() -> None:
    parser = CommandParser()

    # 1. /watch 解析
    cmd = parser.parse("/watch 下载A --log bash://wget -c http://a.com/f.zip --pid 12345")
    assert cmd.tool_name == "watch_task"
    assert cmd.params["alias"] == "下载A"
    assert cmd.params["log"] == "bash://wget -c http://a.com/f.zip"
    assert cmd.params["pid"] == "12345"
    print("[OK] CommandParser /watch")

    # 2. /list 解析
    cmd = parser.parse("/list")
    assert cmd.tool_name == "list_tasks"
    assert cmd.params == {}
    print("[OK] CommandParser /list")

    # 3. 未知命令
    try:
        parser.parse("/unknown")
        raise AssertionError("Should raise ParseError")
    except ParseError:
        print("[OK] CommandParser unknown command")


async def test_intent_parser() -> None:
    response = json.dumps(
        {
            "tool_name": "watch_task",
            "params": {"alias": "下载B", "log": "file://C:\\\\data\\\\dl.log"},
            "missing_params": [],
            "confidence": 0.95,
        }
    )
    provider = FakeProvider(response)
    parser = IntentParser(provider)

    result = await parser.parse("帮我监控下载B，日志在 C:\\data\\dl.log")
    assert result.tool_name == "watch_task"
    assert result.params["alias"] == "下载B"
    assert result.confidence == 0.95
    print("[OK] IntentParser natural language")


async def test_intent_parser_missing_params() -> None:
    response = json.dumps(
        {
            "tool_name": "watch_task",
            "params": {},
            "missing_params": ["alias", "log"],
            "confidence": 0.8,
        }
    )
    provider = FakeProvider(response)
    parser = IntentParser(provider)

    result = await parser.parse("帮我监控一个下载任务")
    assert result.missing_params == ["alias", "log"]
    print("[OK] IntentParser missing params")


async def test_tools() -> None:
    # HelpTool
    help_tool = HelpTool()
    result = await help_tool.execute({})
    assert result.ok
    assert "/watch" in result.data
    print("[OK] HelpTool")

    # QueryProgressTool (mock)
    from unittest.mock import AsyncMock

    metrics = AsyncMock()
    metrics.query_progress = AsyncMock(
        return_value=[
            {
                "alias": "test",
                "percentage": 68.0,
                "speed": "12.5 MB/s",
                "status": "normal",
                "timestamp": "2026-05-10T10:00:00Z",
            }
        ]
    )
    progress_tool = QueryProgressTool(metrics)
    result = await progress_tool.execute({"alias": "test"})
    assert result.ok
    assert result.data["percentage"] == 68.0
    print("[OK] QueryProgressTool")


async def main() -> None:
    await test_command_parser()
    await test_intent_parser()
    await test_intent_parser_missing_params()
    await test_tools()
    print("\n[OK] FR-4 Smoke Test PASSED")


if __name__ == "__main__":
    asyncio.run(main())
