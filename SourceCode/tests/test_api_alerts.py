"""Tests for alert history API.

Relates-to: FR-5
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web

from taskguard.api.routes import TaskHandler, setup_routes


class TestAlertsApi:
    async def test_get_alerts_not_found(self) -> None:
        """GET /api/tasks/{alias}/alerts returns 404 for unknown alias."""
        app = web.Application()
        store = MagicMock()
        store.get = AsyncMock(side_effect=Exception("not found"))
        app["store"] = store
        setup_routes(app)

        request = MagicMock()
        request.match_info = {"alias": "nonexistent"}
        request.app = app

        handler = TaskHandler(store)
        response = await handler.get_alerts(request)
        assert response.status == 404

    async def test_get_alerts_empty(self) -> None:
        """GET /api/tasks/{alias}/alerts returns empty list when no alerts."""
        app = web.Application()
        store = MagicMock()
        store.get = AsyncMock()
        metrics = MagicMock()
        metrics.query_alerts = AsyncMock(return_value=[])
        app["store"] = store
        app["metrics_store"] = metrics
        setup_routes(app)

        request = MagicMock()
        request.match_info = {"alias": "dl"}
        request.app = app

        handler = TaskHandler(store)
        response = await handler.get_alerts(request)
        assert response.status == 200
        body = json.loads(response.text)
        assert body["alerts"] == []

    async def test_get_alerts_with_data(self) -> None:
        """GET /api/tasks/{alias}/alerts returns alert history."""
        app = web.Application()
        store = MagicMock()
        store.get = AsyncMock()
        metrics = MagicMock()
        metrics.query_alerts = AsyncMock(return_value=[
            {
                "id": 1,
                "alias": "dl",
                "timestamp": datetime.now(UTC).isoformat(),
                "rule": "cpu_high",
                "level": "WARNING",
                "message": "CPU high",
                "snapshot": None,
            }
        ])
        app["store"] = store
        app["metrics_store"] = metrics
        setup_routes(app)

        request = MagicMock()
        request.match_info = {"alias": "dl"}
        request.app = app

        handler = TaskHandler(store)
        response = await handler.get_alerts(request)
        assert response.status == 200
        body = json.loads(response.text)
        assert len(body["alerts"]) == 1
        assert body["alerts"][0]["rule"] == "cpu_high"
