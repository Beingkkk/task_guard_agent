"""REST API route handlers.

Relates-to: FR-4
"""

import json
import logging
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aiohttp import web

from taskguard.interaction.intent_parser import IntentParser
from taskguard.llm.base import BaseProvider, LLMError, Message
from taskguard.storage.task_store import TaskStore
from taskguard.tools.base import ToolRegistry, ToolResult
from taskguard.utils.log_source_uri import LogSource

logger = logging.getLogger(__name__)


def json_response(data: dict[str, Any], status: int = 200) -> web.Response:
    """Return a JSON response with the given status."""
    return web.json_response(data, status=status)


def error_response(error_code: str, message: str, status: int = 400) -> web.Response:
    """Return a JSON error response."""
    return json_response({"error": error_code, "message": message}, status=status)


def _tool_result_to_http(result: ToolResult) -> web.Response:
    """Convert a ToolResult to an HTTP response."""
    if result.ok:
        return json_response({"data": result.data} if result.data else {}, status=200)

    status_map: dict[str, int] = {
        "alias_exists": 409,
        "alias_not_found": 404,
        "alias_managed_by_yaml": 403,
        "invalid_alias": 400,
        "invalid_uri": 400,
        "invalid_pid": 400,
        "missing_source": 400,
        "no_changes": 400,
        "invalid_update": 400,
    }
    status_code = status_map.get(result.error_code or "", 400)
    return error_response(
        result.error_code or "unknown",
        result.message or "Unknown error",
        status=status_code,
    )


class TaskHandler:
    """Handler for /api/tasks routes."""

    def __init__(self, store: TaskStore) -> None:
        self._store = store

    async def list_tasks(self, request: web.Request) -> web.Response:
        """GET /api/tasks — list all tasks."""
        tool = ToolRegistry.get("list_tasks")
        if tool is None:
            return error_response("tool_not_found", "list_tasks tool not found", 500)
        result = await tool.execute({"_store": self._store})
        if result.ok:
            return json_response({"tasks": result.data or []})
        return _tool_result_to_http(result)

    async def create_task(self, request: web.Request) -> web.Response:
        """POST /api/tasks — register a new task."""
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return error_response("invalid_json", "Request body must be valid JSON", 400)

        params: dict[str, Any] = {
            "alias": body.get("alias", ""),
            "log": body.get("log", ""),
            "_store": self._store,
        }
        if "pid" in body:
            params["pid"] = body["pid"]
        if "tool_hint" in body:
            params["tool_hint"] = body["tool_hint"]

        tool = ToolRegistry.get("watch_task")
        if tool is None:
            return error_response("tool_not_found", "watch_task tool not found", 500)
        result = await tool.execute(params)

        if result.ok:
            data: dict[str, Any]
            if result.data is not None and hasattr(result.data, "to_dict"):
                data = result.data.to_dict()
            elif result.data is not None:
                data = result.data
            else:
                data = {}
            return json_response(data, status=201)
        return _tool_result_to_http(result)

    async def delete_task(self, request: web.Request) -> web.Response:
        """DELETE /api/tasks/{alias} — unregister a task."""
        alias = request.match_info.get("alias", "")
        tool = ToolRegistry.get("unwatch_task")
        if tool is None:
            return error_response("tool_not_found", "unwatch_task tool not found", 500)
        result = await tool.execute({"alias": alias, "_store": self._store})
        if result.ok:
            return web.Response(status=204)
        return _tool_result_to_http(result)

    async def get_status(self, request: web.Request) -> web.Response:
        """GET /api/tasks/{alias}/status — get task comprehensive status."""
        alias = request.match_info.get("alias", "")

        # Get task registration info
        tool = ToolRegistry.get("query_status")
        if tool is None:
            return error_response("tool_not_found", "query_status tool not found", 500)

        # Check if metrics_store is available
        metrics_store = request.app.get("metrics_store")
        result = await tool.execute({"alias": alias, "_store": self._store, "_metrics_store": metrics_store})
        if result.ok:
            data = result.data if isinstance(result.data, dict) else {}
            return json_response(data)
        return _tool_result_to_http(result)

    async def batch_status(self, request: web.Request) -> web.Response:
        """POST /api/tasks/batch-status — get status for multiple tasks."""
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return error_response("invalid_json", "Request body must be valid JSON", 400)

        aliases = body.get("aliases", [])
        if not isinstance(aliases, list) or not aliases:
            return json_response({"tasks": []})

        tool = ToolRegistry.get("query_batch_status")
        if tool is None:
            return error_response("tool_not_found", "query_batch_status tool not found", 500)

        result = await tool.execute({"aliases": aliases})
        if result.ok:
            data = result.data if isinstance(result.data, dict) else {"tasks": []}
            return json_response(data)
        return _tool_result_to_http(result)

    async def get_alerts(self, request: web.Request) -> web.Response:
        """GET /api/tasks/{alias}/alerts — get alert history for a task."""
        alias = request.match_info.get("alias", "")

        # Verify task exists
        try:
            await self._store.get(alias)
        except Exception:
            return error_response("alias_not_found", f"Task '{alias}' not found", 404)

        metrics_store = request.app.get("metrics_store")
        if metrics_store is None:
            return json_response({"alerts": []})

        since = datetime.now(UTC) - timedelta(days=7)
        try:
            alerts = await metrics_store.query_alerts(alias, since=since, limit=100)
        except Exception as exc:
            logger.exception("Failed to query alerts for %s", alias)
            return error_response("query_failed", str(exc), 500)

        return json_response({"alerts": alerts})

    async def revise_task(self, request: web.Request) -> web.Response:
        """PATCH /api/tasks/{alias} — modify an existing task."""
        alias = request.match_info.get("alias", "")
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return error_response("invalid_json", "Request body must be valid JSON", 400)

        params: dict[str, Any] = {
            "alias": alias,
            "revise": "true",
            "_store": self._store,
        }
        if "log" in body:
            params["log"] = body["log"]
        if "pid" in body:
            params["pid"] = body["pid"]

        tool = ToolRegistry.get("watch_task")
        if tool is None:
            return error_response("tool_not_found", "watch_task tool not found", 500)
        result = await tool.execute(params)

        if result.ok:
            data: dict[str, Any]
            if result.data is not None and hasattr(result.data, "to_dict"):
                data = result.data.to_dict()
            elif result.data is not None:
                data = result.data
            else:
                data = {}
            return json_response(data)
        return _tool_result_to_http(result)


class CollectHandler:
    """Handler for /api/collect route."""

    def __init__(self, store: TaskStore) -> None:
        self._store = store

    async def collect_all(self, request: web.Request) -> web.Response:
        """POST /api/collect — trigger a manual collection cycle."""
        tool = ToolRegistry.get("collect_all")
        if tool is None:
            return error_response("tool_not_found", "collect_all tool not found", 500)
        result = await tool.execute({})
        if result.ok:
            return json_response({"message": "Collection triggered"})
        return _tool_result_to_http(result)


class ProcessHandler:
    """Handler for /api/processes route."""

    async def list_processes(self, request: web.Request) -> web.Response:
        """GET /api/processes — list all running system processes."""
        tool = ToolRegistry.get("list_all_processes")
        if tool is None:
            return error_response("tool_not_found", "list_all_processes tool not found", 500)
        result = await tool.execute({})
        if result.ok:
            return json_response({"processes": result.data or []})
        return _tool_result_to_http(result)


class NaturalLanguageHandler:
    """Handler for /api/natural route."""

    def __init__(self, store: TaskStore, intent_parser: IntentParser | None = None) -> None:
        self._store = store
        self._intent_parser = intent_parser

    async def handle(self, request: web.Request) -> web.Response:
        """POST /api/natural — parse natural language and execute."""
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return error_response("invalid_json", "Request body must be valid JSON", 400)

        text = body.get("text", "").strip()
        if not text:
            return error_response("empty_text", "Text is required", 400)

        if self._intent_parser is None:
            return error_response("no_parser", "Intent parser not available", 503)

        parsed = await self._intent_parser.parse(text)

        if parsed.tool_name == "unknown":
            return json_response(
                {
                    "intent": "unknown",
                    "message": "Could not understand the request",
                    "executed": False,
                }
            )

        if parsed.missing_params:
            return json_response(
                {
                    "intent": parsed.tool_name,
                    "params": parsed.params,
                    "missing_params": parsed.missing_params,
                    "executed": False,
                }
            )

        # Execute the tool
        tool = ToolRegistry.get(parsed.tool_name)
        if tool is None:
            return error_response("tool_not_found", f"Tool '{parsed.tool_name}' not found", 500)

        # Inject store into params
        params = dict(parsed.params)
        params["_store"] = self._store

        result = await tool.execute(params)

        return json_response(
            {
                "intent": parsed.tool_name,
                "params": parsed.params,
                "executed": result.ok,
                "result": result.data if result.ok else None,
                "error": result.message if not result.ok else None,
            }
        )


class TaskLogHandler:
    """Handler for /api/tasks/{alias}/logs and /api/tasks/{alias}/log-info routes."""

    def __init__(self, store: TaskStore) -> None:
        self._store = store

    def _resolve_log_path(self, log_source: LogSource) -> Path | None:
        """Resolve LogSource to a concrete file path."""
        if not log_source.path:
            return None
        source_path = Path(log_source.path)
        if source_path.is_file():
            return source_path
        if source_path.is_dir():
            extensions = log_source.extensions
            files = [p for p in source_path.iterdir() if p.is_file() and p.suffix in extensions]
            if not files:
                return None
            return max(files, key=lambda p: p.stat().st_mtime)
        return None

    def _read_last_n_lines(self, path: Path, n: int) -> list[str]:
        """Read the last n lines from a file."""
        with open(path, encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n\r") for line in deque(f, maxlen=n)]

    async def get_logs(self, request: web.Request) -> web.Response:
        """GET /api/tasks/{alias}/logs?limit=N — read last N log lines."""
        alias = request.match_info.get("alias", "")
        limit_str = request.query.get("limit", "50")
        try:
            limit = int(limit_str)
            if limit < 1:
                limit = 50
            if limit > 1000:
                limit = 1000
        except ValueError:
            limit = 50

        try:
            task = await self._store.get(alias)
        except Exception:
            return error_response("alias_not_found", f"Task '{alias}' not found", 404)

        if task.log_source is None:
            return json_response({"lines": [], "source": None})

        log_path = self._resolve_log_path(task.log_source)
        if log_path is None:
            return error_response("log_not_found", "Log file not found", 404)

        try:
            lines = self._read_last_n_lines(log_path, limit)
        except OSError as exc:
            return error_response("read_error", f"Failed to read log: {exc}", 500)

        return json_response({
            "lines": lines,
            "source": str(log_path),
            "limit": limit,
        })

    async def get_log_info(self, request: web.Request) -> web.Response:
        """GET /api/tasks/{alias}/log-info — get log source metadata."""
        alias = request.match_info.get("alias", "")

        try:
            task = await self._store.get(alias)
        except Exception:
            return error_response("alias_not_found", f"Task '{alias}' not found", 404)

        if task.log_source is None:
            return json_response({"type": "none"})

        log_source = task.log_source
        source_path = Path(log_source.path) if log_source.path else None

        if log_source.is_dir:
            # Directory mode
            if source_path is None or not source_path.is_dir():
                return json_response({
                    "type": "dir",
                    "path": log_source.path,
                    "count": 0,
                    "current_file": None,
                })

            extensions = log_source.extensions
            files = [p for p in source_path.iterdir() if p.is_file() and p.suffix in extensions]
            current_file = max(files, key=lambda p: p.stat().st_mtime) if files else None

            return json_response({
                "type": "dir",
                "path": str(source_path),
                "count": len(files),
                "current_file": str(current_file) if current_file else None,
            })

        # File mode
        if source_path is None:
            return json_response({"type": "file", "path": None, "size": None})

        # Handle multiple files (semicolon-separated) — report primary file
        primary = log_source.paths[0] if log_source.paths else None
        if primary:
            p = Path(primary)
            size = p.stat().st_size if p.is_file() else None
        else:
            size = None

        return json_response({
            "type": "file",
            "path": str(source_path),
            "size": size,
        })


class TaskAskHandler:
    """Handler for /api/tasks/{alias}/ask route — LLM Q&A for a specific task."""

    def __init__(self, store: TaskStore, provider: BaseProvider | None = None) -> None:
        self._store = store
        self._provider = provider

    _ASK_SYSTEM_PROMPT = """\
你是 TaskGuard 智能监控助手。用户正在监控一个进程任务，会向你询问该任务的当前状态。

你需要基于以下任务信息，用中文简洁准确地回答用户的问题。

回答原则：
1. 直接回答用户问题，不要输出无关内容
2. 如果数据不足，明确告知用户
3. 涉及技术状态时，用通俗语言解释
4. 如果进程已退出，提醒用户检查
"""

    async def ask(self, request: web.Request) -> web.Response:
        """POST /api/tasks/{alias}/ask — ask LLM about a task's status."""
        alias = request.match_info.get("alias", "")

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return error_response("invalid_json", "Request body must be valid JSON", 400)

        question = body.get("question", "").strip()
        if not question:
            return error_response("empty_question", "Question is required", 400)

        if self._provider is None:
            return error_response("no_llm", "LLM provider not available", 503)

        # Fetch task status
        tool = ToolRegistry.get("query_status")
        if tool is None:
            return error_response("tool_not_found", "query_status tool not found", 500)

        metrics_store = request.app.get("metrics_store")
        result = await tool.execute({"alias": alias, "_store": self._store, "_metrics_store": metrics_store})
        if not result.ok:
            return _tool_result_to_http(result)

        task_data = result.data if isinstance(result.data, dict) else {}

        # Build context for LLM
        context = self._build_context(alias, task_data)

        try:
            messages = [
                Message(role="user", content=f"{context}\n\n用户问题：{question}"),
            ]
            response = await self._provider.complete(
                system=self._ASK_SYSTEM_PROMPT,
                messages=messages,
            )
            return json_response({"answer": response.content.strip()})
        except LLMError as exc:
            logger.warning("Task ask LLM failed: %s", exc)
            return error_response("llm_error", str(exc), 503)

    def _build_context(self, alias: str, task_data: dict[str, Any]) -> str:
        """Build a context string from task data for the LLM."""
        lines = [f"任务名称: {alias}"]

        pid = task_data.get("pid")
        if pid is not None:
            lines.append(f"进程 PID: {pid}")

        log_source = task_data.get("log_source")
        if log_source:
            lines.append(f"日志路径: {log_source}")

        metrics = task_data.get("latest_metrics")
        if metrics:
            lines.append("\n最新进程指标:")
            lines.append(f"  - 状态: {metrics.get('status', '未知')}")
            lines.append(f"  - CPU: {metrics.get('cpu_percent', 'N/A')}%")
            lines.append(f"  - 内存: {metrics.get('memory_percent', 'N/A')}%")
            lines.append(f"  - 工作集内存: {metrics.get('memory_working_set', 'N/A')} bytes")
            if metrics.get("exit_code") is not None:
                lines.append(f"  - 退出码: {metrics['exit_code']}")

        progress = task_data.get("latest_progress")
        if progress:
            lines.append("\n最新进度:")
            lines.append(f"  - 完成度: {progress.get('percentage', 'N/A')}%")
            lines.append(f"  - 速度: {progress.get('speed', 'N/A')}")
            lines.append(f"  - 预计剩余: {progress.get('eta', 'N/A')}")
            lines.append(f"  - 状态: {progress.get('status', 'N/A')}")

        recent_logs = task_data.get("recent_logs")
        if recent_logs and recent_logs.get("lines"):
            lines.append("\n最近日志 (最多50行):")
            for line in recent_logs["lines"][-20:]:
                lines.append(f"  {line}")

        return "\n".join(lines)


def setup_routes(app: web.Application, provider: BaseProvider | None = None) -> None:
    """Register all REST API routes on the aiohttp app."""
    store: TaskStore = app["store"]
    intent_parser: IntentParser | None = app.get("intent_parser")

    task_handler = TaskHandler(store)
    collect_handler = CollectHandler(store)
    process_handler = ProcessHandler()
    ask_handler = TaskAskHandler(store, provider)
    natural_handler = NaturalLanguageHandler(store, intent_parser)

    log_handler = TaskLogHandler(store)

    # Task routes
    app.router.add_get("/api/tasks", task_handler.list_tasks)
    app.router.add_post("/api/tasks", task_handler.create_task)
    app.router.add_delete("/api/tasks/{alias}", task_handler.delete_task)
    app.router.add_get("/api/tasks/{alias}/status", task_handler.get_status)
    app.router.add_post("/api/tasks/batch-status", task_handler.batch_status)
    app.router.add_get("/api/tasks/{alias}/alerts", task_handler.get_alerts)
    app.router.add_patch("/api/tasks/{alias}", task_handler.revise_task)
    app.router.add_get("/api/tasks/{alias}/logs", log_handler.get_logs)
    app.router.add_get("/api/tasks/{alias}/log-info", log_handler.get_log_info)
    app.router.add_post("/api/tasks/{alias}/ask", ask_handler.ask)

    # Process routes
    app.router.add_get("/api/processes", process_handler.list_processes)

    # Collect route
    app.router.add_post("/api/collect", collect_handler.collect_all)

    # Natural language route (kept for backward compatibility)
    app.router.add_post("/api/natural", natural_handler.handle)
