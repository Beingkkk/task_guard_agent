"""Tests for REST API routes.

Relates-to: FR-4, proposal-0011
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer
from aiohttp.web import Application

from taskguard.api.routes import setup_routes
from taskguard.models.snapshot import ProcessInfo, Snapshot
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore
from taskguard.tools import register_builtin_tools
from taskguard.tools.base import ToolRegistry


@pytest.fixture
async def api_app(tmp_path: Path) -> Application:
    """Create an aiohttp app with routes configured for testing."""
    app = Application()

    # Set up task store with test data
    store = TaskStore(tmp_path)
    await store.load()

    # Set up metrics store so trend/context queries work in tests
    metrics_store = MetricsStore(tmp_path / "metrics.db")
    await metrics_store.open()
    app["metrics_store"] = metrics_store

    register_builtin_tools(store, metrics_store)

    app["store"] = store

    # Set up a mock intent parser for natural language tests
    from unittest.mock import MagicMock

    from taskguard.interaction.intent_parser import IntentParser
    from taskguard.tools.collect_all import CollectAllTool

    mock_parser = AsyncMock(spec=IntentParser)
    app["intent_parser"] = mock_parser

    # Re-register collect_all with a mock harness so it works in tests
    mock_harness = MagicMock()
    mock_harness.run_once = AsyncMock()
    ToolRegistry.register(CollectAllTool(harness=mock_harness))

    setup_routes(app)

    yield app

    await metrics_store.close()


@pytest.fixture
async def client(api_app: Application):
    """Return an aiohttp test client with server started."""
    async with TestClient(TestServer(api_app)) as client:
        yield client


class TestTasksRoutes:
    async def test_list_tasks_empty(self, client: TestClient) -> None:
        """GET /api/tasks returns empty list when no tasks."""
        resp = await client.get("/api/tasks")
        assert resp.status == 200
        data = await resp.json()
        assert data["tasks"] == []

    async def test_create_task(self, client: TestClient, tmp_path: Path) -> None:
        """POST /api/tasks creates a new task."""
        payload = {
            "alias": "smoke",
            "log": str(tmp_path / "test.log"),
            "pid": 12345,
        }
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status == 201
        data = await resp.json()
        assert data["alias"] == "smoke"
        assert data["pid"] == 12345

    async def test_create_task_duplicate_alias(self, client: TestClient, tmp_path: Path) -> None:
        """POST /api/tasks with duplicate alias returns 409."""
        payload = {
            "alias": "dup",
            "log": str(tmp_path / "test.log"),
        }
        resp1 = await client.post("/api/tasks", json=payload)
        assert resp1.status == 201

        resp2 = await client.post("/api/tasks", json=payload)
        assert resp2.status == 409
        data = await resp2.json()
        assert "error" in data

    async def test_delete_task(self, client: TestClient, tmp_path: Path) -> None:
        """DELETE /api/tasks/{alias} removes a task."""
        payload = {
            "alias": "to-delete",
            "log": str(tmp_path / "test.log"),
        }
        await client.post("/api/tasks", json=payload)

        resp = await client.delete("/api/tasks/to-delete")
        assert resp.status == 204

    async def test_delete_nonexistent_task(self, client: TestClient) -> None:
        """DELETE /api/tasks/{alias} for unknown alias returns 404."""
        resp = await client.delete("/api/tasks/nonexistent")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data

    async def test_get_task_status(self, client: TestClient, tmp_path: Path) -> None:
        """GET /api/tasks/{alias}/status returns task status."""
        payload = {
            "alias": "status-test",
            "log": str(tmp_path / "test.log"),
            "pid": 12345,
        }
        await client.post("/api/tasks", json=payload)

        resp = await client.get("/api/tasks/status-test/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["alias"] == "status-test"
        assert "pid" in data
        assert "log_source" in data
        assert "metrics_trend" in data

    async def test_get_status_nonexistent(self, client: TestClient) -> None:
        """GET /api/tasks/{alias}/status for unknown alias returns 404."""
        resp = await client.get("/api/tasks/nonexistent/status")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data

    async def test_batch_status(self, client: TestClient, tmp_path: Path) -> None:
        """POST /api/tasks/batch-status returns statuses for multiple tasks."""
        for alias in ("batch-a", "batch-b"):
            await client.post(
                "/api/tasks",
                json={
                    "alias": alias,
                    "log": str(tmp_path / f"{alias}.log"),
                    "pid": 1000,
                },
            )

        resp = await client.post(
            "/api/tasks/batch-status", json={"aliases": ["batch-a", "batch-b", "missing"]}
        )
        assert resp.status == 200
        data = await resp.json()
        assert "tasks" in data
        assert len(data["tasks"]) == 3

        aliases = {t["alias"] for t in data["tasks"] if "alias" in t}
        assert "batch-a" in aliases
        assert "batch-b" in aliases
        assert "missing" in aliases

    async def test_batch_status_empty(self, client: TestClient) -> None:
        """POST /api/tasks/batch-status with empty aliases returns empty list."""
        resp = await client.post("/api/tasks/batch-status", json={"aliases": []})
        assert resp.status == 200
        data = await resp.json()
        assert data["tasks"] == []


class TestCollectRoute:
    async def test_collect_all(self, client: TestClient) -> None:
        """POST /api/collect triggers collection."""
        resp = await client.post("/api/collect")
        assert resp.status == 200


class TestNaturalRoute:
    async def test_natural_language_parses_and_executes(
        self,
        client: TestClient,
        tmp_path: Path,
        api_app: Application,
    ) -> None:
        """POST /api/natural parses intent and executes."""
        from taskguard.interaction.intent_parser import IntentParseResult

        mock_parser = api_app["intent_parser"]
        mock_parser.parse.return_value = IntentParseResult(
            tool_name="list_tasks",
            params={},
            missing_params=[],
            confidence=1.0,
        )

        payload = {"text": "list all tasks"}
        resp = await client.post("/api/natural", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["intent"] == "list_tasks"

    async def test_natural_language_missing_params(
        self,
        client: TestClient,
        api_app: Application,
    ) -> None:
        """POST /api/natural with missing params returns missing_params."""
        from taskguard.interaction.intent_parser import IntentParseResult

        mock_parser = api_app["intent_parser"]
        mock_parser.parse.return_value = IntentParseResult(
            tool_name="watch_task",
            params={"alias": "下载A"},
            missing_params=["log"],
            confidence=0.8,
        )

        payload = {"text": "监控下载A"}  # missing log path
        resp = await client.post("/api/natural", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["executed"] is False
        assert "missing_params" in data


class TestAskRoute:
    async def test_ask_includes_trend_context(
        self,
        client: TestClient,
        tmp_path: Path,
        api_app: Application,
    ) -> None:
        """POST /api/tasks/{alias}/ask sends trend summary to the LLM."""
        from datetime import UTC, datetime, timedelta

        from taskguard.llm.base import LLMResponse, Usage

        alias = "ask-trend"
        await client.post(
            "/api/tasks",
            json={"alias": alias, "log": str(tmp_path / "trend.log"), "pid": 9999},
        )

        metrics_store: MetricsStore = api_app["metrics_store"]
        now = datetime.now(UTC)
        for i in range(3):
            await metrics_store.save_snapshot(
                Snapshot(
                    task_alias=alias,
                    log_lines=[f"line {i}"],
                    process=ProcessInfo(
                        cpu_percent=float(i * 15),
                        memory_percent=float(30 + i * 5),
                        memory_working_set=1000000,
                        status="running",
                    ),
                    timestamp=now - timedelta(minutes=30 * (2 - i)),
                )
            )

        mock_provider = AsyncMock()
        mock_provider.complete.return_value = LLMResponse(
            content="CPU 呈上升趋势。",
            usage=Usage(input_tokens=100, output_tokens=10),
        )

        # Replace the ask handler's provider with the mock
        api_app["ask_handler"]._provider = mock_provider

        resp = await client.post(f"/api/tasks/{alias}/ask", json={"question": "最近 CPU 怎么样？"})
        assert resp.status == 200
        data = await resp.json()
        assert data["answer"] == "CPU 呈上升趋势。"

        # Verify the LLM was called with trend context
        assert mock_provider.complete.called
        call_args = mock_provider.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[1]
        content = messages[0].content
        assert "指标趋势" in content
        assert "CPU" in content
