"""StateAnalyzer — LLM-based task health summarization.

Relates-to: FR-3
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from taskguard.analyzers.prompts.state_summary_prompt import (
    _STATE_SUMMARY_TOOL,
    STATE_SUMMARY_SYSTEM_PROMPT,
)
from taskguard.llm.base import BaseProvider, LLMError, Message
from taskguard.models.snapshot import Snapshot
from taskguard.models.state_summary import StateSummary
from taskguard.models.task import Task

logger = logging.getLogger(__name__)


class StateAnalyzer:
    """Analyze task health by combining metrics and log snippets via LLM."""

    def __init__(
        self,
        provider: BaseProvider,
        state_analysis_interval: int = 60,
        max_log_lines: int = 50,
    ) -> None:
        self._provider = provider
        self._state_analysis_interval = state_analysis_interval
        self._max_log_lines = max_log_lines

    async def analyze(
        self,
        task: Task,
        snapshot: Snapshot,
        recent_alerts: list[dict[str, Any]] | None = None,
    ) -> StateSummary | None:
        """Generate a StateSummary for the given task snapshot.

        Returns None if the LLM cooldown is active or the provider is unavailable.
        """
        if self._provider is None:
            return None

        # Enforce per-task analysis interval
        now = datetime.now(UTC).timestamp()
        last_analysis = task.state.get("last_state_analysis_call", 0)
        if now - last_analysis < self._state_analysis_interval:
            return None

        process = snapshot.process
        indicators: dict[str, Any] = {
            "cpu_percent": process.cpu_percent if process is not None else None,
            "memory_percent": process.memory_percent if process is not None else None,
            "process_status": process.status if process is not None else None,
            "log_tail": "\n".join(snapshot.log_lines[-self._max_log_lines :]),
            "recent_alerts": [
                f"[{a.get('level')}] {a.get('message')}" for a in (recent_alerts or [])
            ],
        }

        user_content = self._build_user_content(task.alias, snapshot, recent_alerts)

        try:
            response = await self._provider.complete(
                system=STATE_SUMMARY_SYSTEM_PROMPT,
                messages=[Message(role="user", content=user_content)],
                tools=[_STATE_SUMMARY_TOOL],
            )
        except LLMError as exc:
            logger.warning("State analysis LLM failed for %s: %s", task.alias, exc)
            return None
        except Exception:
            logger.exception("Unexpected error in state analysis for %s", task.alias)
            return None

        if not response.tool_calls:
            logger.warning("State analysis LLM returned no tool calls for %s", task.alias)
            return None

        tc = response.tool_calls[0]
        try:
            args: dict[str, Any] = json.loads(tc.arguments)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse state summary tool arguments for %s: %s", task.alias, exc)
            return None

        task.state["last_state_analysis_call"] = datetime.now(UTC).timestamp()

        return StateSummary(
            status=args.get("status", "unknown"),
            summary=args.get("summary", ""),
            indicators=args.get("indicators", indicators),
            confidence=args.get("confidence", 0.0),
            analyzed_by="llm",
        )

    def _build_user_content(
        self,
        alias: str,
        snapshot: Snapshot,
        recent_alerts: list[dict[str, Any]] | None,
    ) -> str:
        """Build the user-facing prompt content for the LLM."""
        lines = [f"任务名称: {alias}"]

        process = snapshot.process
        if process is not None:
            lines.append("\n当前进程指标:")
            lines.append(f"  - 状态: {process.status or '未知'}")
            lines.append(
                f"  - CPU: {process.cpu_percent}%"
                if process.cpu_percent is not None
                else "  - CPU: N/A"
            )
            lines.append(
                f"  - 内存占用: {process.memory_percent}%"
                if process.memory_percent is not None
                else "  - 内存占用: N/A"
            )
            lines.append(
                f"  - 工作集内存: {process.memory_working_set} bytes"
                if process.memory_working_set is not None
                else "  - 工作集内存: N/A"
            )
            if process.exit_code is not None:
                lines.append(f"  - 退出码: {process.exit_code}")
        else:
            lines.append("\n当前进程指标: 无")

        if recent_alerts:
            lines.append("\n最近告警:")
            for alert in recent_alerts[-5:]:
                lines.append(
                    f"  - [{alert.get('level')}] {alert.get('rule')}: {alert.get('message')}"
                )

        if snapshot.log_lines:
            lines.append(f"\n最近日志 (最多 {self._max_log_lines} 行):")
            for line in snapshot.log_lines[-self._max_log_lines :]:
                lines.append(f"  {line}")
        else:
            lines.append("\n最近日志: 无")

        return "\n".join(lines)
