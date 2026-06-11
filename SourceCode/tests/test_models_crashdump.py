"""Tests for CrashDump data model.

Relates-to: FR-6
"""

from datetime import UTC, datetime

from taskguard.crash.models import CrashDump


class TestCrashDump:
    def test_construction(self) -> None:
        ts = datetime(2026, 5, 30, 10, 0, 0, tzinfo=UTC)
        dump = CrashDump(
            alias="download_a",
            timestamp=ts,
            exit_code=-1073741819,
            last_logs=["ERROR: out of memory", "Process terminated"],
            peak_cpu=95.2,
            peak_memory=2147483648,
            peak_memory_percent=85.5,
            metrics_timeline=[
                {"timestamp": "2026-05-30T09:59:00Z", "cpu_percent": 90.0, "memory_working_set": 2000000000},
            ],
            system_memory={"total": 8589934592, "available": 1073741824, "percent_used": 87.5},
            reason="process_exited",
        )
        assert dump.alias == "download_a"
        assert dump.timestamp == ts
        assert dump.exit_code == -1073741819
        assert dump.last_logs == ["ERROR: out of memory", "Process terminated"]
        assert dump.peak_cpu == 95.2
        assert dump.peak_memory == 2147483648
        assert dump.peak_memory_percent == 85.5
        assert dump.reason == "process_exited"

    def test_default_fields(self) -> None:
        ts = datetime.now(UTC)
        dump = CrashDump(
            alias="test",
            timestamp=ts,
            reason="process_exited",
        )
        assert dump.exit_code is None
        assert dump.last_logs == []
        assert dump.peak_cpu is None
        assert dump.peak_memory is None
        assert dump.peak_memory_percent is None
        assert dump.metrics_timeline == []
        assert dump.system_memory == {}

    def test_to_dict(self) -> None:
        ts = datetime(2026, 5, 30, 10, 0, 0, tzinfo=UTC)
        dump = CrashDump(
            alias="download_a",
            timestamp=ts,
            exit_code=1,
            last_logs=["line1"],
            peak_cpu=50.0,
            peak_memory=1024,
            peak_memory_percent=10.0,
            metrics_timeline=[{"cpu_percent": 50.0}],
            system_memory={"total": 8192},
            reason="process_exited",
        )
        d = dump.to_dict()
        assert d["alias"] == "download_a"
        assert d["timestamp"] == "2026-05-30T10:00:00Z"
        assert d["exit_code"] == 1
        assert d["last_logs"] == ["line1"]
        assert d["peak_cpu"] == 50.0
        assert d["peak_memory"] == 1024
        assert d["peak_memory_percent"] == 10.0
        assert d["metrics_timeline"] == [{"cpu_percent": 50.0}]
        assert d["system_memory"] == {"total": 8192}
        assert d["reason"] == "process_exited"

    def test_to_dict_none_exit_code(self) -> None:
        ts = datetime(2026, 5, 30, 10, 0, 0, tzinfo=UTC)
        dump = CrashDump(
            alias="test",
            timestamp=ts,
            reason="process_exited",
            exit_code=None,
        )
        d = dump.to_dict()
        assert d["exit_code"] is None

    def test_from_dict(self) -> None:
        data = {
            "alias": "download_a",
            "timestamp": "2026-05-30T10:00:00Z",
            "exit_code": -1,
            "last_logs": ["line1", "line2"],
            "peak_cpu": 75.5,
            "peak_memory": 2048,
            "peak_memory_percent": 50.0,
            "metrics_timeline": [{"cpu_percent": 75.5}],
            "system_memory": {"total": 4096},
            "reason": "memory_drop",
        }
        dump = CrashDump.from_dict(data)
        assert dump.alias == "download_a"
        assert dump.timestamp == datetime(2026, 5, 30, 10, 0, 0, tzinfo=UTC)
        assert dump.exit_code == -1
        assert dump.last_logs == ["line1", "line2"]
        assert dump.peak_cpu == 75.5
        assert dump.peak_memory == 2048
        assert dump.peak_memory_percent == 50.0
        assert dump.reason == "memory_drop"

    def test_from_dict_roundtrip(self) -> None:
        ts = datetime.now(UTC)
        original = CrashDump(
            alias="test",
            timestamp=ts,
            exit_code=42,
            last_logs=["a", "b"],
            peak_cpu=99.9,
            peak_memory=1234,
            peak_memory_percent=45.6,
            metrics_timeline=[{"x": 1}],
            system_memory={"y": 2},
            reason="process_exited",
        )
        d = original.to_dict()
        restored = CrashDump.from_dict(d)
        assert restored.alias == original.alias
        assert restored.timestamp == original.timestamp
        assert restored.exit_code == original.exit_code
        assert restored.last_logs == original.last_logs
        assert restored.peak_cpu == original.peak_cpu
        assert restored.peak_memory == original.peak_memory
        assert restored.peak_memory_percent == original.peak_memory_percent
        assert restored.metrics_timeline == original.metrics_timeline
        assert restored.system_memory == original.system_memory
        assert restored.reason == original.reason

    def test_from_dict_missing_optional_fields(self) -> None:
        data = {
            "alias": "minimal",
            "timestamp": "2026-05-30T10:00:00Z",
            "reason": "process_exited",
        }
        dump = CrashDump.from_dict(data)
        assert dump.alias == "minimal"
        assert dump.exit_code is None
        assert dump.last_logs == []
        assert dump.peak_cpu is None
        assert dump.peak_memory is None
        assert dump.metrics_timeline == []
        assert dump.system_memory == {}
