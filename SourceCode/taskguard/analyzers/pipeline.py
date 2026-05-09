"""AnalyzerPipeline — regex-first, LLM-fallback progress extraction.

Relates-to: FR-3
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from taskguard.analyzers.regex_extractor import RegexExtractor
from taskguard.llm.base import BaseProvider, LLMError, ToolDefinition
from taskguard.models.snapshot import ProgressInfo, Snapshot
from taskguard.models.task import Task

logger = logging.getLogger(__name__)

_PROGRESS_TOOL = ToolDefinition(
    name="progress_extract",
    description="从日志中提取进度信息",
    input_schema={
        "type": "object",
        "properties": {
            "percentage": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
            "speed": {"type": ["string", "null"]},
            "eta": {"type": ["string", "null"]},
            "status": {
                "enum": ["normal", "stalled", "error", "complete", "unknown"],
            },
            "raw_summary": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["percentage", "status", "raw_summary", "confidence"],
    },
)

_SYSTEM_PROMPT = (
    "你是一名日志分析助手。你的任务是从程序日志中提取进度信息。\n"
    "规则：\n"
    "1. 只返回 JSON 格式的结构化数据\n"
    '2. 如果无法识别进度，percentage 设为 null，status 设为 "unknown"\n'
    "3. speed 和 eta 保留原始字符串（含单位）\n"
    "4. 给出一个人类可读的 raw_summary（一句话）"
)


class AnalyzerPipeline:
    """Regex-first, LLM-fallback progress extraction pipeline."""

    def __init__(
        self,
        provider: BaseProvider,
        regex_extractor: RegexExtractor,
        llm_min_interval: int = 60,
        max_log_lines: int = 50,
        regex_threshold: float = 0.6,
    ) -> None:
        self._provider = provider
        self._regex_extractor = regex_extractor
        self._llm_min_interval = llm_min_interval
        self._max_log_lines = max_log_lines
        self._regex_threshold = regex_threshold

    async def analyze(self, task: Task, snapshot: Snapshot) -> ProgressInfo | None:
        """Extract progress from snapshot log lines."""
        log_lines = snapshot.log_lines
        if not log_lines:
            return None

        # 1. Try regex first
        regex_result = self._regex_extractor.extract(log_lines, task.config.tool_hint)

        if regex_result is not None and regex_result.confidence >= self._regex_threshold:
            return regex_result

        # 2. Check LLM cooldown
        now = datetime.now(UTC).timestamp()
        last_llm = task.state.get("last_llm_call", 0)
        if now - last_llm < self._llm_min_interval:
            # Cooldown active: return low-confidence regex result or None
            return regex_result

        # 3. LLM fallback
        trimmed = log_lines[-self._max_log_lines :]
        user_content = "\n".join(trimmed)

        from taskguard.llm.base import Message

        messages = [Message(role="user", content=user_content)]

        try:
            response = await self._provider.complete(
                system=_SYSTEM_PROMPT,
                messages=messages,
                tools=[_PROGRESS_TOOL],
            )
        except LLMError as exc:
            logger.warning("LLM fallback failed for %s: %s", task.alias, exc)
            return None
        except Exception:
            logger.exception("Unexpected error in LLM fallback for %s", task.alias)
            return None

        if not response.tool_calls:
            logger.warning("LLM returned no tool calls for %s", task.alias)
            return None

        tc = response.tool_calls[0]
        try:
            args: dict[str, Any] = json.loads(tc.arguments)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM tool arguments for %s: %s", task.alias, exc)
            return None

        # Update cooldown timestamp
        task.state["last_llm_call"] = datetime.now(UTC).timestamp()

        return ProgressInfo(
            percentage=args.get("percentage"),
            speed=args.get("speed"),
            eta=args.get("eta"),
            status=args.get("status", "unknown"),
            raw_summary=args.get("raw_summary", ""),
            confidence=args.get("confidence", 0.0),
            extracted_by="llm",
        )
