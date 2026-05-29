"""WebSocket connection manager for real-time event streaming.

Relates-to: FR-4
"""

import json
import logging
from typing import Any

from aiohttp import web

from taskguard.api.events import EventPublisher

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self, publisher: EventPublisher | None = None) -> None:
        self.connections: set[web.WebSocketResponse] = set()
        self._publisher = publisher
        self._subscribe_all()

    def _subscribe_all(self) -> None:
        """Subscribe to all event types from the publisher."""
        if self._publisher is None:
            return
        for event_type in (
            "task.updated",
            "task.alert",
            "task.oom",
            "task.stalled",
            "task.recovered",
        ):
            self._publisher.subscribe(event_type, self._make_broadcast_callback(event_type))

    def _make_broadcast_callback(self, event_type: str) -> Any:
        """Create a callback that broadcasts events of a specific type."""

        async def callback(data: dict[str, Any]) -> None:
            await self.send_event(event_type, data)

        return callback

    async def handle(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a new WebSocket connection."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections.add(ws)
        logger.debug("WebSocket client connected. Total: %d", len(self.connections))

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                        if payload.get("type") == "ping":
                            await ws.send_json({"type": "pong"})
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error("WebSocket error: %s", ws.exception())
        finally:
            self.connections.discard(ws)
            logger.debug("WebSocket client disconnected. Total: %d", len(self.connections))

        return ws

    async def send_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Send an event to all connected clients."""
        message = {"type": event_type, "data": data}
        dead_connections: set[web.WebSocketResponse] = set()

        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.add(ws)

        for ws in dead_connections:
            self.connections.discard(ws)


def setup_websocket_routes(app: web.Application) -> None:
    """Register WebSocket route on the aiohttp app."""
    ws_manager: WebSocketManager = app["ws_manager"]
    app.router.add_get("/ws", ws_manager.handle)
