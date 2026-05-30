"""Alert data model for FR-5.

Relates-to: FR-5
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

__all__ = ["Alert"]


@dataclass(slots=True)
class Alert:
    """An alert triggered by a rule evaluation."""

    rule: str
    level: Literal["INFO", "WARNING", "CRITICAL"]
    message: str
    timestamp: datetime
    snapshot: dict[str, Any] = field(default_factory=dict)
