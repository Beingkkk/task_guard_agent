"""Regex-based progress extraction.

Relates-to: FR-3
"""

import importlib
import inspect
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from taskguard.models.snapshot import ProgressInfo


@dataclass(frozen=True)
class RegexTemplate:
    """A regex template for extracting progress from a specific tool."""

    name: str
    patterns: list[str]
    confidence_fn: Callable[[dict[str, str]], float]


class RegexExtractor:
    """Extracts progress information using regex templates."""

    def __init__(self, templates: list[RegexTemplate]) -> None:
        self._templates = templates

    @classmethod
    def from_builtin_templates(cls) -> "RegexExtractor":
        """Collect all templates from analyzers/regex/*.py modules."""
        from taskguard.analyzers import regex as regex_pkg

        templates: list[RegexTemplate] = []
        pkg_path = Path(regex_pkg.__file__).parent
        for _, mod_name, _ in pkgutil.iter_modules([str(pkg_path)]):
            if mod_name.startswith("_"):
                continue
            mod = importlib.import_module(f"taskguard.analyzers.regex.{mod_name}")
            for _, obj in inspect.getmembers(mod):
                if isinstance(obj, RegexTemplate):
                    templates.append(obj)
        return cls(templates)

    def extract(
        self,
        log_lines: list[str],
        tool_hint: str | None = None,
    ) -> ProgressInfo | None:
        """Try templates and return the highest-confidence match."""
        candidates: list[tuple[float, ProgressInfo]] = []

        templates = self._templates
        if tool_hint is not None:
            templates = [t for t in templates if t.name == tool_hint]

        for template in templates:
            for pattern in template.patterns:
                for line in log_lines:
                    match = re.search(pattern, line)
                    if match:
                        groups = match.groupdict()
                        confidence = template.confidence_fn(groups)
                        info = self._build_progress(groups, confidence)
                        candidates.append((confidence, info))

        if not candidates:
            return None

        # Return highest confidence
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _build_progress(self, groups: dict[str, str], confidence: float) -> ProgressInfo:
        """Build ProgressInfo from regex match groups."""
        pct_raw = groups.get("pct") or groups.get("percentage")
        percentage = float(pct_raw) if pct_raw is not None else None

        speed = groups.get("spd") or groups.get("speed")
        eta = groups.get("eta")

        return ProgressInfo(
            percentage=percentage,
            speed=speed,
            eta=eta,
            status="normal" if percentage is not None and percentage < 100 else "complete",
            raw_summary=f"进度 {percentage}%" if percentage is not None else "",
            confidence=confidence,
            extracted_by="regex",
        )
