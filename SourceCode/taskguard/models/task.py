"""Task data models.

Relates-to: FR-1
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from taskguard.utils.log_source_uri import LogSource

__all__ = ["LogSource", "TaskConfig", "Task"]


@dataclass(slots=True, frozen=True)
class TaskConfig:
    """Per-task configuration overrides."""

    collect_interval: int = 30
    stalled_threshold: int = 300
    llm_min_interval: int = 60
    alert_cooldown: int = 300
    cpu_warning: int = 90
    memory_warning: int = 80
    memory_critical: int = 95


@dataclass(slots=True)
class Task:
    """A monitored task definition."""

    alias: str
    log_source: LogSource
    pid: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    state: dict[str, Any] = field(default_factory=dict)
    config: TaskConfig = field(default_factory=TaskConfig)
    source: str = "cli"

    def __post_init__(self) -> None:
        if "/" in self.alias or " " in self.alias or "\x00" in self.alias:
            raise ValueError(f"Invalid alias: {self.alias!r}")
        if self.pid is not None and self.pid <= 0:
            raise ValueError(f"PID must be a positive integer, got {self.pid}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "alias": self.alias,
            "pid": self.pid,
            "log_source": {
                "type": self.log_source.type,
                "command": self.log_source.command,
                "path": self.log_source.path,
                "extensions": list(self.log_source.extensions),
            },
            "created_at": (self.created_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
            "state": self.state,
            "config": {
                "collect_interval": self.config.collect_interval,
                "stalled_threshold": self.config.stalled_threshold,
                "llm_min_interval": self.config.llm_min_interval,
                "alert_cooldown": self.config.alert_cooldown,
                "cpu_warning": self.config.cpu_warning,
                "memory_warning": self.config.memory_warning,
                "memory_critical": self.config.memory_critical,
            },
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Restore from a dict produced by to_dict()."""
        log_data = data["log_source"]
        log_source = LogSource(
            type=log_data["type"],
            command=log_data.get("command"),
            path=log_data.get("path"),
            extensions=tuple(log_data.get("extensions", [".log", ".txt", ".out"])),
        )

        config_data = data.get("config", {})
        config = TaskConfig(
            collect_interval=config_data.get("collect_interval", 30),
            stalled_threshold=config_data.get("stalled_threshold", 300),
            llm_min_interval=config_data.get("llm_min_interval", 60),
            alert_cooldown=config_data.get("alert_cooldown", 300),
            cpu_warning=config_data.get("cpu_warning", 90),
            memory_warning=config_data.get("memory_warning", 80),
            memory_critical=config_data.get("memory_critical", 95),
        )

        created_raw = data.get("created_at")
        if created_raw:
            if created_raw.endswith("Z"):
                created_raw = created_raw[:-1] + "+00:00"
            created_at = datetime.fromisoformat(created_raw)
        else:
            created_at = datetime.now(UTC)

        return cls(
            alias=data["alias"],
            pid=data.get("pid"),
            log_source=log_source,
            created_at=created_at,
            state=data.get("state", {}),
            config=config,
            source=data.get("source", "cli"),
        )
