"""Tests for Alert data model.

Relates-to: FR-5
"""

from datetime import UTC, datetime

from taskguard.models.alert import Alert


class TestAlert:
    def test_construction(self) -> None:
        ts = datetime(2026, 5, 30, 10, 0, 0, tzinfo=UTC)
        alert = Alert(
            rule="cpu_high",
            level="WARNING",
            message="CPU 95% for 5min",
            timestamp=ts,
            snapshot={"cpu_percent": 95.0},
        )
        assert alert.rule == "cpu_high"
        assert alert.level == "WARNING"
        assert alert.message == "CPU 95% for 5min"
        assert alert.timestamp == ts
        assert alert.snapshot == {"cpu_percent": 95.0}

    def test_default_snapshot(self) -> None:
        alert = Alert(
            rule="process_exited",
            level="CRITICAL",
            message="Process exited",
            timestamp=datetime.now(UTC),
        )
        assert alert.snapshot == {}

    def test_critical_level(self) -> None:
        alert = Alert(
            rule="memory_critical",
            level="CRITICAL",
            message="Memory > 95%",
            timestamp=datetime.now(UTC),
        )
        assert alert.level == "CRITICAL"

    def test_info_level(self) -> None:
        alert = Alert(
            rule="progress_complete",
            level="INFO",
            message="Progress 100%",
            timestamp=datetime.now(UTC),
        )
        assert alert.level == "INFO"
