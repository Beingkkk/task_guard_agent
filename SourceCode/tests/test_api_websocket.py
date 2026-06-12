"""Tests for WebSocket manager.

Relates-to: FR-4
"""

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from aiohttp.web import Application

from taskguard.api.events import EventPublisher
from taskguard.api.websocket import WebSocketManager, setup_websocket_routes


@pytest.fixture
async def ws_app(tmp_path: Path) -> Application:
    """Create an aiohttp app with WebSocket configured for testing."""
    app = Application()
    publisher = EventPublisher()
    ws_manager = WebSocketManager(publisher)

    app["event_publisher"] = publisher
    app["ws_manager"] = ws_manager
    setup_websocket_routes(app)

    return app


@pytest.fixture
async def ws_client(ws_app: Application):
    """Return an aiohttp test client with server started."""
    async with TestClient(TestServer(ws_app)) as client:
        yield client


class TestWebSocket:
    async def test_websocket_connection(self, ws_client: TestClient) -> None:
        """Client can connect to /ws endpoint."""
        async with ws_client.ws_connect("/ws") as ws:
            assert ws.closed is False

    async def test_websocket_receives_events(
        self, ws_app: Application, ws_client: TestClient
    ) -> None:
        """Published events are broadcast to WebSocket clients."""
        publisher: EventPublisher = ws_app["event_publisher"]

        async with ws_client.ws_connect("/ws") as ws:
            await publisher.publish("task.updated", {"alias": "test"})

            msg = await ws.receive_json(timeout=1.0)
            assert msg["type"] == "task.updated"
            assert msg["data"]["alias"] == "test"

    async def test_multiple_clients_receive_events(
        self, ws_app: Application, ws_client: TestClient
    ) -> None:
        """Events are broadcast to all connected clients."""
        publisher: EventPublisher = ws_app["event_publisher"]

        async with ws_client.ws_connect("/ws") as ws1, ws_client.ws_connect("/ws") as ws2:
            await publisher.publish("task.updated", {"alias": "test"})

            msg1 = await ws1.receive_json(timeout=1.0)
            msg2 = await ws2.receive_json(timeout=1.0)

            assert msg1["type"] == "task.updated"
            assert msg2["type"] == "task.updated"

    async def test_client_disconnect_cleanup(
        self, ws_app: Application, ws_client: TestClient
    ) -> None:
        """Disconnected clients are removed from active set."""
        ws_manager: WebSocketManager = ws_app["ws_manager"]

        async with ws_client.ws_connect("/ws"):
            pass  # connection auto-closes on exit

        # After context exit, client should be removed
        assert len(ws_manager.connections) == 0
