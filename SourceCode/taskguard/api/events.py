"""Event publisher for broadcasting task updates.

Relates-to: FR-4
"""

import contextlib
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class EventPublisher:
    """In-memory event publisher using Observer pattern.

    Subscribers register callbacks for specific event types.
    When an event is published, all matching callbacks are invoked.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventCallback]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """Register a callback for an event type."""
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: EventCallback) -> None:
        """Remove a callback for an event type."""
        if event_type in self._subscribers:
            with contextlib.suppress(ValueError):
                self._subscribers[event_type].remove(callback)

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to all subscribers of the given type."""
        callbacks = list(self._subscribers.get(event_type, []))
        for callback in callbacks:
            try:
                await callback(data)
            except Exception:
                logger.exception("Event callback failed for %s", event_type)
