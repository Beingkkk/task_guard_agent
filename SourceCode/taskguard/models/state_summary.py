"""State summary model for LLM-based task health analysis.

Relates-to: FR-3
"""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(slots=True)
class StateSummary:
    """Structured result of LLM task-state analysis.

    Unlike ProgressInfo (which focuses on download/processing progress),
    StateSummary describes the overall health of a monitored task by
    combining process metrics and recent log lines.
    """

    status: Literal["healthy", "stalled", "error", "unknown"] = "unknown"
    summary: str = ""
    indicators: dict[str, Any] = None  # type: ignore[assignment]
    confidence: float = 0.0
    analyzed_by: Literal["llm"] = "llm"

    def __post_init__(self) -> None:
        if self.indicators is None:
            self.indicators = {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for API responses and storage."""
        return {
            "status": self.status,
            "summary": self.summary,
            "indicators": self.indicators,
            "confidence": self.confidence,
            "analyzed_by": self.analyzed_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateSummary":
        """Deserialize from a plain dict."""
        return cls(
            status=data.get("status", "unknown"),
            summary=data.get("summary", ""),
            indicators=data.get("indicators", {}),
            confidence=data.get("confidence", 0.0),
            analyzed_by=data.get("analyzed_by", "llm"),
        )
