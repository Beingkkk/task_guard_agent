"""FR-3 Smoke Test — pure mock, no real API calls.

Relates-to: FR-3
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from taskguard.analyzers.pipeline import AnalyzerPipeline
from taskguard.analyzers.regex_extractor import RegexExtractor
from taskguard.llm.base import BaseProvider, LLMResponse, ToolCall, Usage
from taskguard.models.snapshot import Snapshot
from taskguard.models.task import Task, TaskConfig
from taskguard.storage.metrics_store import MetricsStore
from taskguard.utils.log_source_uri import LogSource


class FakeProvider(BaseProvider):
    """Mock provider that always returns a fixed progress."""

    async def complete(self, system, messages, tools=None):
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


async def main():
    # 1. Prepare regex extractor
    extractor = RegexExtractor.from_builtin_templates()

    # 2. Prepare fake provider
    provider = FakeProvider()

    # 3. Build AnalyzerPipeline
    pipeline = AnalyzerPipeline(
        provider=provider,
        regex_extractor=extractor,
        llm_min_interval=0,  # Disable cooldown for testing
        max_log_lines=50,
        regex_threshold=0.6,
    )

    # 4. Test regex success (wget progress)
    task = Task(
        alias="smoke-wget",
        log_source=LogSource(type="bash", command="wget http://example.com/file.zip"),
        config=TaskConfig(tool_hint="wget"),
    )
    log_lines = [
        "--2026-05-09 10:00:00--  http://example.com/file.zip",
        "Resolving example.com... 93.184.216.34",
        "Connecting to example.com|93.184.216.34|:80... connected.",
        "HTTP request sent, awaiting response... 200 OK",
        "Length: 104857600 (100M) [application/zip]",
        "Saving to: 'file.zip'",
        "",
        "file.zip              68%[==================>      ]  68.00M  12.5MB/s    eta 42s",
    ]
    snapshot = Snapshot(task_alias=task.alias, log_lines=log_lines)
    progress = await pipeline.analyze(task, snapshot)
    assert progress is not None
    assert progress.extracted_by == "regex"
    assert progress.percentage == 68.0
    print(f"Regex: {progress}")

    # 5. Test LLM fallback (unknown tool logs)
    task2 = Task(
        alias="smoke-unknown",
        log_source=LogSource(type="bash", command="./custom_tool"),
    )
    log_lines2 = ["Processing item 42 of 100...", "Item 42 done", "Processing item 43..."]
    snapshot2 = Snapshot(task_alias=task2.alias, log_lines=log_lines2)
    progress2 = await pipeline.analyze(task2, snapshot2)
    assert progress2 is not None
    assert progress2.extracted_by == "llm"
    assert progress2.percentage == 75.0
    print(f"LLM fallback: {progress2}")

    # 6. Test cooldown
    task3 = Task(
        alias="smoke-cooldown",
        log_source=LogSource(type="bash", command="./custom_tool"),
    )
    pipeline_cool = AnalyzerPipeline(
        provider=provider,
        regex_extractor=extractor,
        llm_min_interval=3600,  # 1 hour cooldown
    )
    progress3 = await pipeline_cool.analyze(task3, snapshot2)
    # First triggers LLM
    assert progress3 is not None and progress3.extracted_by == "llm"
    # Second immediate call should be in cooldown, returns None or regex
    progress4 = await pipeline_cool.analyze(task3, snapshot2)
    assert progress4 is None or progress4.extracted_by == "regex"
    print(
        f"Cooldown: first={progress3.extracted_by}, second={progress4.extracted_by if progress4 else None}"
    )

    # 7. Verify SQLite writes
    db_path = Path("data/smoke_fr3.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    metrics = MetricsStore(db_path)
    await metrics.open()
    await metrics.save_progress(task.alias, datetime.now(UTC), progress)
    await metrics.save_llm_usage(
        task2.alias,
        datetime.now(UTC),
        "kimi-for-coding",
        input_tokens=100,
        output_tokens=50,
        latency_ms=1200,
    )
    rows = await metrics.query_progress(task.alias, datetime.min.replace(tzinfo=UTC))
    assert len(rows) >= 1, f"Expected at least 1 progress row, got {len(rows)}"
    assert rows[0]["percentage"] == 68.0
    print(f"SQLite progress rows: {len(rows)}, first: {rows[0]}")
    await metrics.close()

    print("\n[PASS] FR-3 Smoke Test PASSED")


if __name__ == "__main__":
    asyncio.run(main())
