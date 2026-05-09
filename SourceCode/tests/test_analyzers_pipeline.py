"""Tests for AnalyzerPipeline.

Relates-to: FR-3
"""

from unittest import mock

import pytest

from taskguard.analyzers.pipeline import AnalyzerPipeline
from taskguard.analyzers.regex_extractor import RegexExtractor, RegexTemplate
from taskguard.llm.base import BaseProvider, LLMError, LLMResponse, ToolCall, Usage
from taskguard.models.snapshot import Snapshot
from taskguard.models.task import Task
from taskguard.utils.log_source_uri import LogSource


class FakeProvider(BaseProvider):
    """Mock provider that returns a fixed progress."""

    def __init__(self) -> None:
        self.call_count = 0

    async def complete(self, system, messages, tools=None):
        self.call_count += 1
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="progress_extract",
                    arguments=b'{"percentage": 75.0, "speed": "10 MB/s", "eta": "5 min", "status": "normal", "raw_summary": "downloading 75%", "confidence": 0.95}',
                )
            ],
            usage=Usage(input_tokens=100, output_tokens=50),
        )


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def high_confidence_extractor() -> RegexExtractor:
    tpl = RegexTemplate(
        name="high",
        patterns=[r"(?P<pct>\d+)%"],
        confidence_fn=lambda g: 0.8,
    )
    return RegexExtractor([tpl])


@pytest.fixture
def low_confidence_extractor() -> RegexExtractor:
    tpl = RegexTemplate(
        name="low",
        patterns=[r"(?P<pct>\d+)%"],
        confidence_fn=lambda g: 0.3,
    )
    return RegexExtractor([tpl])


@pytest.fixture
def no_match_extractor() -> RegexExtractor:
    return RegexExtractor([])


@pytest.mark.asyncio
async def test_regex_high_confidence_skips_llm(
    fake_provider: FakeProvider,
    high_confidence_extractor: RegexExtractor,
) -> None:
    pipeline = AnalyzerPipeline(
        provider=fake_provider,
        regex_extractor=high_confidence_extractor,
        llm_min_interval=0,
        regex_threshold=0.6,
    )
    task = Task(alias="t", log_source=LogSource(type="bash", command="x"))
    snapshot = Snapshot(task_alias="t", log_lines=["Progress 68%"])

    result = await pipeline.analyze(task, snapshot)

    assert result is not None
    assert result.extracted_by == "regex"
    assert fake_provider.call_count == 0


@pytest.mark.asyncio
async def test_regex_low_confidence_with_cooldown_passed_calls_llm(
    fake_provider: FakeProvider,
    low_confidence_extractor: RegexExtractor,
) -> None:
    pipeline = AnalyzerPipeline(
        provider=fake_provider,
        regex_extractor=low_confidence_extractor,
        llm_min_interval=0,
        regex_threshold=0.6,
    )
    task = Task(alias="t", log_source=LogSource(type="bash", command="x"))
    snapshot = Snapshot(task_alias="t", log_lines=["Progress 68%"])

    result = await pipeline.analyze(task, snapshot)

    assert result is not None
    assert result.extracted_by == "llm"
    assert result.percentage == 75.0
    assert fake_provider.call_count == 1


@pytest.mark.asyncio
async def test_regex_low_confidence_cooldown_active_returns_regex(
    fake_provider: FakeProvider,
    low_confidence_extractor: RegexExtractor,
) -> None:
    pipeline = AnalyzerPipeline(
        provider=fake_provider,
        regex_extractor=low_confidence_extractor,
        llm_min_interval=3600,
        regex_threshold=0.6,
    )
    task = Task(alias="t", log_source=LogSource(type="bash", command="x"))
    # Simulate a recent LLM call
    task.state["last_llm_call"] = 9999999999.0  # far future, cooldown active
    snapshot = Snapshot(task_alias="t", log_lines=["Progress 68%"])

    result = await pipeline.analyze(task, snapshot)

    # Should return low-confidence regex result, not call LLM
    assert result is not None
    assert result.extracted_by == "regex"
    assert fake_provider.call_count == 0


@pytest.mark.asyncio
async def test_no_match_with_cooldown_passed_calls_llm(
    fake_provider: FakeProvider,
    no_match_extractor: RegexExtractor,
) -> None:
    pipeline = AnalyzerPipeline(
        provider=fake_provider,
        regex_extractor=no_match_extractor,
        llm_min_interval=0,
    )
    task = Task(alias="t", log_source=LogSource(type="bash", command="x"))
    snapshot = Snapshot(task_alias="t", log_lines=["Some random text"])

    result = await pipeline.analyze(task, snapshot)

    assert result is not None
    assert result.extracted_by == "llm"
    assert fake_provider.call_count == 1


@pytest.mark.asyncio
async def test_empty_log_lines_returns_none(
    fake_provider: FakeProvider,
    no_match_extractor: RegexExtractor,
) -> None:
    pipeline = AnalyzerPipeline(
        provider=fake_provider,
        regex_extractor=no_match_extractor,
    )
    task = Task(alias="t", log_source=LogSource(type="bash", command="x"))
    snapshot = Snapshot(task_alias="t", log_lines=[])

    result = await pipeline.analyze(task, snapshot)

    assert result is None
    assert fake_provider.call_count == 0


@pytest.mark.asyncio
async def test_provider_error_returns_none(
    fake_provider: FakeProvider,
    no_match_extractor: RegexExtractor,
) -> None:
    class ErrorProvider(BaseProvider):
        async def complete(self, system, messages, tools=None):
            raise LLMError("boom")

    pipeline = AnalyzerPipeline(
        provider=ErrorProvider(),
        regex_extractor=no_match_extractor,
        llm_min_interval=0,
    )
    task = Task(alias="t", log_source=LogSource(type="bash", command="x"))
    snapshot = Snapshot(task_alias="t", log_lines=["text"])

    result = await pipeline.analyze(task, snapshot)

    assert result is None


@pytest.mark.asyncio
async def test_max_log_lines_trims_to_last_50(
    fake_provider: FakeProvider,
    no_match_extractor: RegexExtractor,
) -> None:
    pipeline = AnalyzerPipeline(
        provider=fake_provider,
        regex_extractor=no_match_extractor,
        llm_min_interval=0,
        max_log_lines=50,
    )
    task = Task(alias="t", log_source=LogSource(type="bash", command="x"))
    log_lines = [f"Line {i}" for i in range(100)]
    snapshot = Snapshot(task_alias="t", log_lines=log_lines)

    with mock.patch.object(
        fake_provider, "complete", wraps=fake_provider.complete
    ) as mock_complete:
        await pipeline.analyze(task, snapshot)

        call_args = mock_complete.call_args
        messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
        # The user message should contain only last 50 lines
        user_msg = [m for m in messages if m.role == "user"][0]
        assert "Line 50" in user_msg.content
        assert "Line 0" not in user_msg.content
        assert "Line 99" in user_msg.content
