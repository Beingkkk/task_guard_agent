"""Tests for Provider schema dataclasses.

Relates-to: FR-3
"""

from taskguard.llm.base import (
    LLMError,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
    Usage,
)


class TestMessage:
    def test_basic_construction(self) -> None:
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"
        assert m.tool_calls == []
        assert m.tool_call_id is None

    def test_with_tool_calls(self) -> None:
        tc = ToolCall(id="1", name="progress_extract", arguments=b'{"p":1}')
        m = Message(role="assistant", content="", tool_calls=[tc])
        assert len(m.tool_calls) == 1
        assert m.tool_calls[0].name == "progress_extract"


class TestToolCall:
    def test_construction(self) -> None:
        tc = ToolCall(id="1", name="progress_extract", arguments=b'{"p":1}')
        assert tc.id == "1"
        assert tc.name == "progress_extract"
        assert tc.arguments == b'{"p":1}'


class TestToolDefinition:
    def test_construction(self) -> None:
        td = ToolDefinition(
            name="x",
            description="y",
            input_schema={"type": "object"},
        )
        assert td.name == "x"
        assert td.description == "y"
        assert td.input_schema == {"type": "object"}


class TestLLMResponse:
    def test_construction(self) -> None:
        r = LLMResponse(
            content="",
            tool_calls=[],
            usage=Usage(10, 5),
        )
        assert r.content == ""
        assert r.tool_calls == []
        assert r.usage is not None
        assert r.usage.input_tokens == 10
        assert r.usage.output_tokens == 5


class TestLLMError:
    def test_is_exception(self) -> None:
        err = LLMError("something went wrong")
        assert isinstance(err, Exception)
        assert str(err) == "something went wrong"
