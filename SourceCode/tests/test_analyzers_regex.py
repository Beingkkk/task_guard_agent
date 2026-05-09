"""Tests for RegexExtractor.

Relates-to: FR-3
"""

import pytest

from taskguard.analyzers.regex_extractor import RegexExtractor, RegexTemplate


@pytest.fixture
def extractor() -> RegexExtractor:
    return RegexExtractor.from_builtin_templates()


class TestWget:
    def test_wget_progress_line(self, extractor: RegexExtractor) -> None:
        lines = [
            "--2026-05-09 10:00:00--  http://example.com/file.zip",
            "Resolving example.com... 93.184.216.34",
            "file.zip              68%[==================>      ]  68.00M  12.5MB/s    eta 42s",
        ]
        result = extractor.extract(lines)
        assert result is not None
        assert result.extracted_by == "regex"
        assert result.percentage == 68.0
        assert result.speed == "12.5MB/s"
        assert result.eta == "42s"
        assert result.confidence > 0.5


class TestRsync:
    def test_rsync_progress_line(self, extractor: RegexExtractor) -> None:
        lines = [
            "sending incremental file list",
            "    100M  68%   12.50MB/s    0:00:42",
        ]
        result = extractor.extract(lines)
        assert result is not None
        assert result.extracted_by == "regex"
        assert result.percentage == 68.0
        assert result.speed == "12.50MB/s"


class TestNoMatch:
    def test_no_matching_lines(self, extractor: RegexExtractor) -> None:
        lines = ["Some random log output", "Nothing special here"]
        result = extractor.extract(lines)
        assert result is None


class TestToolHint:
    def test_tool_hint_filters_templates(self, extractor: RegexExtractor) -> None:
        # This log could match either wget or rsync depending on regex design
        # With tool_hint="wget", only wget template should run
        lines = [
            "file.zip              68%[==================>      ]  68.00M  12.5MB/s    eta 42s",
        ]
        result = extractor.extract(lines, tool_hint="wget")
        assert result is not None
        assert result.percentage == 68.0

    def test_tool_hint_no_match(self, extractor: RegexExtractor) -> None:
        lines = [
            "file.zip              68%[==================>      ]  68.00M  12.5MB/s    eta 42s",
        ]
        result = extractor.extract(lines, tool_hint="rsync")
        # wget line should not match rsync template
        assert result is None


class TestConfidence:
    def test_higher_confidence_wins(self) -> None:
        # Create two templates: one always matches with low confidence, one with high
        low_tpl = RegexTemplate(
            name="low",
            patterns=[r"(?P<pct>\d+)%"],
            confidence_fn=lambda m: 0.3,
        )
        high_tpl = RegexTemplate(
            name="high",
            patterns=[r"(?P<pct>\d+)%.*(?P<spd>\d+\.?\d*\w+/s)"],
            confidence_fn=lambda m: 0.9,
        )
        ext = RegexExtractor([low_tpl, high_tpl])
        lines = ["Download 68% at 12.5MB/s"]
        result = ext.extract(lines)
        assert result is not None
        assert result.confidence == 0.9


class TestBuiltinTemplates:
    def test_from_builtin_templates_not_empty(self) -> None:
        extractor = RegexExtractor.from_builtin_templates()
        assert len(extractor._templates) > 0
