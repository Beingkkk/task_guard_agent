"""Tests for EventPublisher.

Relates-to: FR-4
"""

import pytest

from taskguard.api.events import EventPublisher


@pytest.fixture
def publisher() -> EventPublisher:
    return EventPublisher()


class TestEventPublisher:
    async def test_subscribe_and_publish(self, publisher: EventPublisher) -> None:
        """Subscribed callback receives published events."""
        received: list[dict] = []

        async def callback(data: dict) -> None:
            received.append(data)

        publisher.subscribe("task.updated", callback)
        await publisher.publish("task.updated", {"alias": "test"})

        assert len(received) == 1
        assert received[0]["alias"] == "test"

    async def test_multiple_subscribers_same_event(self, publisher: EventPublisher) -> None:
        """All subscribers for the same event type receive the event."""
        received1: list[dict] = []
        received2: list[dict] = []

        async def callback1(data: dict) -> None:
            received1.append(data)

        async def callback2(data: dict) -> None:
            received2.append(data)

        publisher.subscribe("task.updated", callback1)
        publisher.subscribe("task.updated", callback2)
        await publisher.publish("task.updated", {"alias": "test"})

        assert len(received1) == 1
        assert len(received2) == 1

    async def test_unsubscribe(self, publisher: EventPublisher) -> None:
        """Unsubscribed callback no longer receives events."""
        received: list[dict] = []

        async def callback(data: dict) -> None:
            received.append(data)

        publisher.subscribe("task.updated", callback)
        publisher.unsubscribe("task.updated", callback)
        await publisher.publish("task.updated", {"alias": "test"})

        assert len(received) == 0

    async def test_different_event_types_isolated(self, publisher: EventPublisher) -> None:
        """Subscribers for one event type don't receive another."""
        received: list[dict] = []

        async def callback(data: dict) -> None:
            received.append(data)

        publisher.subscribe("task.updated", callback)
        await publisher.publish("task.alert", {"alias": "test"})

        assert len(received) == 0

    async def test_callback_exception_does_not_affect_others(
        self, publisher: EventPublisher,
    ) -> None:
        """If one callback raises, others still receive the event."""
        received: list[dict] = []

        async def bad_callback(_data: dict) -> None:
            raise RuntimeError("boom")

        async def good_callback(data: dict) -> None:
            received.append(data)

        publisher.subscribe("task.updated", bad_callback)
        publisher.subscribe("task.updated", good_callback)
        await publisher.publish("task.updated", {"alias": "test"})

        assert len(received) == 1

    async def test_publish_with_no_subscribers(self, publisher: EventPublisher) -> None:
        """Publishing with no subscribers does not raise."""
        await publisher.publish("task.updated", {"alias": "test"})  # should not raise
