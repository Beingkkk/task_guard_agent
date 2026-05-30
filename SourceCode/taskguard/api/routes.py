"""REST API route handlers.

Relates-to: FR-4
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import web

from taskguard.interaction.intent_parser import IntentParser
from taskguard.storage.task_store import TaskStore
from taskguard.tools.base import ToolRegistry, ToolResult

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


def setup_routes(app: web.Application) -> None:
    """Register all REST API routes on the aiohttp app."""
    store: TaskStore = app["store"]
    intent_parser: IntentParser | None = app.get("intent_parser")

    task_handler = TaskHandler(store)
    collect_handler = CollectHandler(store)
    natural_handler = NaturalLanguageHandler(store, intent_parser)

    # Task routes
    app.router.add_get("/api/tasks", task_handler.list_tasks)
    app.router.add_post("/api/tasks", task_handler.create_task)
    app.router.add_delete("/api/tasks/{alias}", task_handler.delete_task)
    app.router.add_get("/api/tasks/{alias}/status", task_handler.get_status)
    app.router.add_get("/api/tasks/{alias}/alerts", task_handler.get_alerts)
    app.router.add_patch("/api/tasks/{alias}", task_handler.revise_task)

    # Collect route
    app.router.add_post("/api/collect", collect_handler.collect_all)

    # Natural language route
    app.router.add_post("/api/natural", natural_handler.handle)
