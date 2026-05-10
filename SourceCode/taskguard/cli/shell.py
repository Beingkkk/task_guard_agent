"""Interactive shell for TaskGuard Agent.

Relates-to: FR-4
"""

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from taskguard.agent import AgentHarness
from taskguard.analyzers.pipeline import AnalyzerPipeline
from taskguard.analyzers.regex_extractor import RegexExtractor
from taskguard.collectors.bash_collector import BashCollector
from taskguard.collectors.file_collector import FileCollector
from taskguard.config_loader import ConfigLoader
from taskguard.interaction.intent_parser import IntentParser, IntentParseResult
from taskguard.interaction.parser import CommandParser, ParseError
from taskguard.llm.base import BaseProvider
from taskguard.llm.factory import LLMConfig, create_provider
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore
from taskguard.tools import register_builtin_tools
from taskguard.tools.base import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ShellContext:
    """Transient state for follow-up questions."""

    last_intent: IntentParseResult | None = None
    pending_question: str | None = None


class InteractiveShell:
    """REPL shell with background AgentHarness."""

    def __init__(
        self,
        harness: AgentHarness,
        store: TaskStore,
        metrics_store: MetricsStore,
        provider: BaseProvider | None = None,
    ) -> None:
        self._harness = harness
        self._store = store
        self._metrics_store = metrics_store
        self._provider = provider
        self._parser = CommandParser()
        self._intent_parser = IntentParser(provider)
        self._context = ShellContext()
        self._prompt = "> "
        self._harness_task: asyncio.Task[Any] | None = None

    @classmethod
    async def from_config(cls, config_dir: Path, data_dir: Path) -> "InteractiveShell":
        """Factory: assemble full agent environment from config."""
        data_dir.mkdir(parents=True, exist_ok=True)

        app_config = ConfigLoader.load(config_dir)

        store = TaskStore(data_dir)
        await store.load()

        metrics = MetricsStore(data_dir / "metrics.db")
        await metrics.open()

        harness = AgentHarness(
            store,
            metrics,
            collect_interval=app_config.collect_interval,
        )
        harness.register_collector("bash", BashCollector())
        harness.register_collector("file", FileCollector())

        provider: BaseProvider | None = None
        if app_config.llm.api_key:
            provider = create_provider(
                LLMConfig(
                    provider=app_config.llm.provider,
                    model=app_config.llm.model,
                    api_key=app_config.llm.api_key,
                    base_url=app_config.llm.base_url,
                )
            )
            harness.analyzer = AnalyzerPipeline(
                provider=provider,
                regex_extractor=RegexExtractor.from_builtin_templates(),
                llm_min_interval=app_config.llm.min_interval,
                max_log_lines=app_config.llm.max_log_lines,
                regex_threshold=app_config.llm.regex_threshold,
            )

        register_builtin_tools(store, metrics)

        return cls(harness, store, metrics, provider)

    async def _print_banner(self) -> None:
        llm_status = "ready" if self._provider else "unavailable"
        task_count = len(self._store.list_all())
        data_dir = self._store._state_file.parent

        last_collected_str = "never"
        try:
            last_ts = await self._metrics_store.get_last_collect_time()
            if last_ts:
                ago = int((datetime.now(UTC) - last_ts).total_seconds())
                last_collected_str = f"{ago}s ago"
        except Exception:
            pass

        banner = f"""\
============================================================
  TaskGuard Agent  v0.1
------------------------------------------------------------
  Data dir        : {data_dir}
  Collect interval: {self._harness._interval}s
  LLM provider    : {llm_status}
  Tasks           : {task_count} registered
  Last collected  : {last_collected_str}
------------------------------------------------------------
  Type /help for commands, or just chat with me.
  Type exit to quit.
============================================================
"""
        print(banner)

    async def run(self) -> None:
        """Start harness and enter REPL loop."""
        await self._print_banner()

        self._harness_task = asyncio.create_task(self._harness.run())

        try:
            while True:
                try:
                    user_input: str = await asyncio.to_thread(input, self._prompt)
                except EOFError:
                    break

                stripped = user_input.strip()
                if not stripped:
                    continue

                if stripped.lower() in ("exit", "quit", "q"):
                    break

                try:
                    output = await self._handle_input(stripped)
                    if output:
                        print(output)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Error handling input")
                    print(f"Error: {exc}")

        finally:
            await self._cleanup()

    async def _handle_input(self, user_input: str) -> str:
        """Process a single user input and return output text."""
        if user_input.startswith("/"):
            if user_input.strip() == "/help":
                return self._help_text()

            try:
                parsed = self._parser.parse(user_input)
            except ParseError as exc:
                return f"Parse error: {exc}"

            return await self._execute_tool(parsed.tool_name, parsed.params)

        # Natural language input
        # Check if we have a pending follow-up question
        if self._context.pending_question is not None and self._context.last_intent is not None:
            missing = self._context.last_intent.missing_params
            if missing:
                self._context.last_intent.params[missing[0]] = user_input
                self._context.last_intent.missing_params = missing[1:]

            if self._context.last_intent.missing_params:
                next_param = self._context.last_intent.missing_params[0]
                self._context.pending_question = f"Please provide {next_param}:"
                return f"Please provide {next_param}:"

            # All params collected, execute
            result = self._context.last_intent
            self._context.last_intent = None
            self._context.pending_question = None
            return await self._execute_tool(result.tool_name, result.params)

        # Fresh natural language input
        intent = await self._intent_parser.parse(user_input)

        if intent.confidence < 0.5:
            return (
                "I'm not sure what you mean. Please use /help for available commands, or rephrase."
            )

        if intent.missing_params:
            self._context.last_intent = intent
            self._context.pending_question = intent.missing_params[0]
            return f"Please provide {intent.missing_params[0]}:"

        if intent.tool_name == "unknown":
            return "I couldn't understand that. Please use /help for available commands."

        return await self._execute_tool(intent.tool_name, intent.params)

    async def _execute_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        """Execute a tool and return formatted output."""
        try:
            tool = ToolRegistry.get(tool_name)
        except KeyError:
            return f"Unknown tool: '{tool_name}'"

        try:
            result: ToolResult = await tool.execute(params)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool execution failed: %s", tool_name)
            return f"Error executing {tool_name}: {exc}"

        if not result.ok:
            return result.message or result.error_code or "Error"

        if result.data is None:
            return "Done."

        if isinstance(result.data, str):
            return result.data

        if isinstance(result.data, list):
            if not result.data:
                return "No items."
            # Enhance list output with real-time PID status for list_tasks
            if tool_name == "list_tasks":
                data = await self._enrich_list_with_pid_status(result.data)
                return self._format_table(data)
            return self._format_table(result.data)

        if isinstance(result.data, dict):
            if tool_name == "query_status":
                return self._format_dict_markdown(result.data)
            return "\n".join(f"  {k}: {v}" for k, v in result.data.items())

        return str(result.data)

    async def _enrich_list_with_pid_status(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Add real-time pid_status column to task list."""
        enriched = []
        for row in rows:
            r = dict(row)
            pid = r.get("pid")
            if pid is not None:
                r["pid_status"] = "running" if psutil.pid_exists(int(pid)) else "exited"
            else:
                r["pid_status"] = "-"
            enriched.append(r)
        return enriched

    def _format_dict_markdown(self, data: dict[str, Any]) -> str:
        """Format a task dict as Markdown for readable display."""
        lines: list[str] = []

        alias = data.get("alias", "Unknown")
        lines.append(f"## Task: {alias}")
        lines.append("")

        # Basic info table
        lines.append("| 字段 | 值 |")
        lines.append("|---|---|")
        for key in ("alias", "pid", "created_at", "source"):
            if key in data:
                lines.append(f"| {key} | {data[key]} |")
        lines.append("")

        # Log source
        log_source = data.get("log_source")
        if log_source and isinstance(log_source, dict):
            lines.append("### 日志源")
            lines.append("```json")
            lines.append(json.dumps(log_source, indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")

        # Config
        config = data.get("config")
        if config and isinstance(config, dict):
            lines.append("### 配置")
            lines.append("| 字段 | 值 |")
            lines.append("|---|---|")
            for k, v in config.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")

        # Runtime state
        state = data.get("state")
        if state and isinstance(state, dict) and state:
            lines.append("### 运行时状态")
            lines.append("```json")
            lines.append(json.dumps(state, indent=2, ensure_ascii=False))
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def _format_table(self, rows: list[dict[str, Any]]) -> str:
        """Simple table formatter for list output."""
        if not rows:
            return "No items."
        headers = list(rows[0].keys())
        lines = ["  ".join(f"{h:<15}" for h in headers), "-" * (len(headers) * 17)]
        for row in rows:
            lines.append("  ".join(f"{str(row.get(h, '')):<15}" for h in headers))
        return "\n".join(lines)

    def _help_text(self) -> str:
        """Return help text."""
        return """\
可用命令：

  /watch <别名> --log <URI> [--pid <PID>]    注册监控任务
  /unwatch <别名>                            注销监控任务
  /list                                      列出所有任务
  /status <别名>                             查询任务详情
  /progress <别名>                           查询最新进度
  /cleanup                                   清理已退出的任务
  /help                                      显示此帮助

你也可以用自然语言描述你的操作意图，例如：
  "帮我监控下载A，日志在 C:\\data\\dl.log"
  "现在有哪些任务在跑？"

  exit / quit / q                            退出 Agent
"""

    async def _cleanup(self) -> None:
        """Graceful shutdown."""
        print("\nShutting down...")
        self._harness.shutdown()
        if self._harness_task:
            with suppress(asyncio.CancelledError):
                await self._harness_task
        await self._metrics_store.close()
        print("Goodbye.")
