"""End-to-end API tests with full server, store, and harness.

Relates-to: FR-4
T130: 启动完整服务（内存 SQLite + tmp_path），验证 HTTP 注册任务 → 查询 → 注销、
WebSocket 事件推送、自然语言 POST 端到端。
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from aiohttp.web import Application

from taskguard.agent import AgentHarness
from taskguard.api.events import EventPublisher
from taskguard.api.routes import setup_routes
from taskguard.api.websocket import WebSocketManager, setup_websocket_routes
from taskguard.collectors.file_collector import FileCollector
from taskguard.interaction.intent_parser import IntentParser, IntentParseResult
from taskguard.storage.metrics_store import MetricsStore
from taskguard.storage.task_store import TaskStore
from taskguard.tools import register_builtin_tools
from taskguard.tools.base import ToolRegistry
from taskguard.tools.collect_all import CollectAllTool


@pytest.fixture
async def e2e_app(tmp_path: Path) -> Application:
    """Create a fully configured aiohttp app for end-to-end testing."""
    store = TaskStore(tmp_path)
    await store.load()
    metrics = MetricsStore(tmp_path / "metrics.db")
    await metrics.open()

    harness = AgentHarness(store, metrics, collect_interval=30)
    harness.register_collector("file", FileCollector())

    # Register tools with real harness so collect_all triggers actual collection
    register_builtin_tools(store, metrics)
    ToolRegistry.register(CollectAllTool(harness=harness, metrics_store=metrics))

    app = web.Application()
    publisher = EventPublisher()
    ws_manager = WebSocketManager(publisher)

    app["store"] = store
    app["metrics_store"] = metrics
    app["event_publisher"] = publisher
    app["ws_manager"] = ws_manager

    # Set intent_parser BEFORE setup_routes so NaturalLanguageHandler picks it up
    mock_parser = AsyncMock(spec=IntentParser)
    app["intent_parser"] = mock_parser

    setup_routes(app)
    setup_websocket_routes(app)

    # Wire event publisher into harness (same as APIServer._create_app)
    harness.event_publisher = publisher

    return app


@pytest.fixture
async def e2e_client(e2e_app: Application):
    """Return an aiohttp test client with server started."""
    async with TestClient(TestServer(e2e_app)) as client:
        yield client


class TestE2EHttpLifecycle:
    """End-to-end HTTP CRUD lifecycle tests."""

    async def test_register_query_delete_lifecycle(
        self, e2e_client: TestClient, tmp_path: Path
    ) -> None:
        """Register → list → status → delete → verify gone."""
        log_path = tmp_path / "e2e.log"
        log_path.write_text("test log line\n", encoding="utf-8")

        # 1. Register
        payload = {
            "alias": "e2e-smoke",
            "log": str(log_path),
            "pid": os.getpid(),
        }
        resp = await e2e_client.post("/api/tasks", json=payload)
        assert resp.status == 201
        data = await resp.json()
        assert data["alias"] == "e2e-smoke"

        # 2. List
        resp = await e2e_client.get("/api/tasks")
        assert resp.status == 200
        data = await resp.json()
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["alias"] == "e2e-smoke"

        # 3. Status
        resp = await e2e_client.get("/api/tasks/e2e-smoke/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["alias"] == "e2e-smoke"

        # 4. Delete
        resp = await e2e_client.delete("/api/tasks/e2e-smoke")
        assert resp.status == 204

        # 5. Verify gone
        resp = await e2e_client.get("/api/tasks")
        assert resp.status == 200
        data = await resp.json()
        assert data["tasks"] == []

    async def test_natural_language_end_to_end(
        self, e2e_client: TestClient, e2e_app: Application, tmp_path: Path
    ) -> None:
        """POST /api/natural parses intent, executes tool, returns result."""
        mock_parser = e2e_app["intent_parser"]
        mock_parser.parse.return_value = IntentParseResult(
            tool_name="list_tasks",
            params={},
            missing_params=[],
            confidence=1.0,
        )

        resp = await e2e_client.post("/api/natural", json={"text": "查看所有任务"})
        assert resp.status == 200
        data = await resp.json()
        assert data["intent"] == "list_tasks"
        assert data["executed"] is True
        assert data["result"] is not None

    async def test_natural_language_missing_params(
        self, e2e_client: TestClient, e2e_app: Application
    ) -> None:
        """POST /api/natural with missing params returns missing_params."""
        mock_parser = e2e_app["intent_parser"]
        mock_parser.parse.return_value = IntentParseResult(
            tool_name="watch_task",
            params={"alias": "下载A"},
            missing_params=["log"],
            confidence=0.8,
        )

        resp = await e2e_client.post("/api/natural", json={"text": "监控下载A"})
        assert resp.status == 200
        data = await resp.json()
        assert data["executed"] is False
        assert "missing_params" in data


class TestE2EWebSocketEvents:
    """End-to-end WebSocket event streaming tests."""

    async def test_websocket_receives_task_updated_after_collect(
        self, e2e_client: TestClient, e2e_app: Application, tmp_path: Path
    ) -> None:
        """Connect WS, register task, trigger collect, receive task.updated event."""
        log_path = tmp_path / "ws-test.log"
        log_path.write_text("log line alpha\nlog line beta\n", encoding="utf-8")

        # 1. Connect WebSocket
        async with e2e_client.ws_connect("/ws") as ws:
            # 2. Register task via HTTP
            payload = {
                "alias": "ws-task",
                "log": str(log_path),
                "pid": os.getpid(),
            }
            resp = await e2e_client.post("/api/tasks", json=payload)
            assert resp.status == 201

            # 3. Trigger collection via HTTP
            resp = await e2e_client.post("/api/collect")
            assert resp.status == 200

            # 4. Wait for task.updated event on WebSocket
            msg = await ws.receive_json(timeout=2.0)
            assert msg["type"] == "task.updated"
            assert msg["data"]["alias"] == "ws-task"
            assert "timestamp" in msg["data"]
            assert "metrics" in msg["data"]
            assert "log_lines" in msg["data"]
            assert "log line alpha" in msg["data"]["log_lines"]
            assert "log line beta" in msg["data"]["log_lines"]

    async def test_multiple_ws_clients_receive_same_event(
        self, e2e_client: TestClient, e2e_app: Application, tmp_path: Path
    ) -> None:
        """Multiple WebSocket clients all receive the same task.updated event."""
        log_path = tmp_path / "multi-ws.log"
        log_path.write_text("multi client test\n", encoding="utf-8")

        async with e2e_client.ws_connect("/ws") as ws1, e2e_client.ws_connect("/ws") as ws2:
            payload = {
                "alias": "multi-ws",
                "log": str(log_path),
                "pid": os.getpid(),
            }
            await e2e_client.post("/api/tasks", json=payload)
            await e2e_client.post("/api/collect")

            msg1 = await ws1.receive_json(timeout=2.0)
            msg2 = await ws2.receive_json(timeout=2.0)

            assert msg1["type"] == "task.updated"
            assert msg1["data"]["alias"] == "multi-ws"
            assert msg2["type"] == "task.updated"
            assert msg2["data"]["alias"] == "multi-ws"

    async def test_ws_no_event_after_task_deleted(
        self, e2e_client: TestClient, e2e_app: Application, tmp_path: Path
    ) -> None:
        """Deleted task no longer generates events on collect."""
        log_path = tmp_path / "deleted.log"
        log_path.write_text("will be deleted\n", encoding="utf-8")

        async with e2e_client.ws_connect("/ws") as ws:
            payload = {
                "alias": "deleted-task",
                "log": str(log_path),
                "pid": os.getpid(),
            }
            await e2e_client.post("/api/tasks", json=payload)

            # Collect once to get initial event
            await e2e_client.post("/api/collect")
            await ws.receive_json(timeout=2.0)

            # Delete task
            await e2e_client.delete("/api/tasks/deleted-task")

            # Collect again — no event should arrive
            await e2e_client.post("/api/collect")

            # Wait a short time and verify no message arrives
            with pytest.raises(TimeoutError):
                await ws.receive_json(timeout=0.3)

    async def test_event_publisher_none_does_not_crash(
        self, e2e_client: TestClient, e2e_app: Application, tmp_path: Path
    ) -> None:
        """Server works correctly even when event_publisher is temporarily None."""
        log_path = tmp_path / "no-pub.log"
        log_path.write_text("no publisher\n", encoding="utf-8")

        # Disconnect event publisher
        publisher: EventPublisher = e2e_app["event_publisher"]
        # Clear all subscribers so events are silently dropped
        publisher._subscribers.clear()

        payload = {
            "alias": "no-pub-task",
            "log": str(log_path),
            "pid": os.getpid(),
        }
        resp = await e2e_client.post("/api/tasks", json=payload)
        assert resp.status == 201

        resp = await e2e_client.post("/api/collect")
        assert resp.status == 200
        # Should not crash even though no one is subscribed
