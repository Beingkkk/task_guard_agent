"""Tests for StateAnalyzer.

Relates-to: FR-3
"""

import pytest

from taskguard.analyzers.state_analyzer import StateAnalyzer
from taskguard.llm.base import LLMResponse, Message, ToolCall, Usage
from taskguard.models.snapshot import ProcessInfo, Snapshot
from taskguard.models.state_summary import StateSummary
from taskguard.models.task import Task


class FakeProvider:
    """A fake LLM provider that returns a predefined state summary."""

    def __init__(self, response: LLMResponse) -> None:
        self.response = response
        self.calls: list[tuple[str | None, list[Message]]] = []

    async def complete(
        self,
        system: str | None,
        messages: list[Message],
        tools: list | None = None,
    ) -> LLMResponse:
        self.calls.append((system, messages))
        return self.response


@pytest.fixture
def task() -> Task:
    return Task(alias="test-task", pid=1234)


@pytest.fixture
def snapshot() -> Snapshot:
    return Snapshot(
        task_alias="test-task",
        log_lines=["line1", "line2"],
        process=ProcessInfo(
            cpu_percent=12.5,
            memory_percent=34.0,
            status="running",
        ),
    )


def _make_response(status: str, summary: str, confidence: float) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[
            ToolCall(
                id="call-1",
                name="state_summary",
                arguments=(
                    f'{{"status": "{status}", '
                    f'"summary": "{summary}", '
                    f'"indicators": {{"cpu_percent": 12.5, "memory_percent": 34.0}}, '
                    f'"confidence": {confidence}}}'
                ).encode(),
            )
        ],
        usage=Usage(input_tokens=100, output_tokens=50),
    )


class TestStateAnalyzer:
    async def test_analyze_returns_summary(self, task: Task, snapshot: Snapshot) -> None:
        provider = FakeProvider(_make_response("healthy", "任务运行正常", 0.9))
        analyzer = StateAnalyzer(provider=provider, state_analysis_interval=0)

        result = await analyzer.analyze(task, snapshot)

        assert isinstance(result, StateSummary)
        assert result.status == "healthy"
        assert result.summary == "任务运行正常"
        assert result.confidence == 0.9
        assert result.analyzed_by == "llm"
        assert provider.calls

    async def test_analyze_respects_interval(self, task: Task, snapshot: Snapshot) -> None:
        provider = FakeProvider(_make_response("healthy", "任务运行正常", 0.9))
        analyzer = StateAnalyzer(provider=provider, state_analysis_interval=60)

        # First call should go through
        result1 = await analyzer.analyze(task, snapshot)
        assert result1 is not None
        assert len(provider.calls) == 1

        # Immediate second call should be skipped
        result2 = await analyzer.analyze(task, snapshot)
        assert result2 is None
        assert len(provider.calls) == 1

    async def test_analyze_includes_alerts_in_prompt(self, task: Task, snapshot: Snapshot) -> None:
        provider = FakeProvider(_make_response("error", "检测到异常", 0.8))
        analyzer = StateAnalyzer(provider=provider, state_analysis_interval=0)
        alerts = [{"level": "WARNING", "rule": "cpu_high", "message": "CPU 过高"}]

        await analyzer.analyze(task, snapshot, recent_alerts=alerts)

        _system, messages = provider.calls[0]
        assert "最近告警" in messages[0].content
        assert "CPU 过高" in messages[0].content

    async def test_analyze_handles_llm_error(self, task: Task, snapshot: Snapshot) -> None:
        from taskguard.llm.base import LLMError

        class FailingProvider:
            async def complete(self, system, messages, tools=None):
                raise LLMError("boom")

        analyzer = StateAnalyzer(provider=FailingProvider(), state_analysis_interval=0)  # type: ignore[arg-type]
        result = await analyzer.analyze(task, snapshot)
        assert result is None

    async def test_analyze_no_tool_calls_returns_none(self, task: Task, snapshot: Snapshot) -> None:
        provider = FakeProvider(LLMResponse(content="no tool call"))
        analyzer = StateAnalyzer(provider=provider, state_analysis_interval=0)
        result = await analyzer.analyze(task, snapshot)
        assert result is None
