"""CrashDump data model for FR-6 OOM/scene preservation.

Relates-to: FR-6
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CrashDump:
    """A preserved crash/OOM scene."""

    alias: str
    timestamp: datetime
    exit_code: int | None = None
    last_logs: list[str] = field(default_factory=list)
    peak_cpu: float | None = None
    peak_memory: int | None = None
    peak_memory_percent: float | None = None
    metrics_timeline: list[dict[str, Any]] = field(default_factory=list)
    system_memory: dict[str, Any] = field(default_factory=dict)
    reason: str = "process_exited"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "alias": self.alias,
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "exit_code": self.exit_code,
            "last_logs": self.last_logs,
            "peak_cpu": self.peak_cpu,
            "peak_memory": self.peak_memory,
            "peak_memory_percent": self.peak_memory_percent,
            "metrics_timeline": self.metrics_timeline,
            "system_memory": self.system_memory,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrashDump":
        """Restore from a dict."""
        ts_str = data.get("timestamp", "")
        timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return cls(
            alias=data["alias"],
            timestamp=timestamp,
            exit_code=data.get("exit_code"),
            last_logs=data.get("last_logs", []),
            peak_cpu=data.get("peak_cpu"),
            peak_memory=data.get("peak_memory"),
            peak_memory_percent=data.get("peak_memory_percent"),
            metrics_timeline=data.get("metrics_timeline", []),
            system_memory=data.get("system_memory", {}),
            reason=data.get("reason", "process_exited"),
        )
