"""curl progress regex template.

Relates-to: FR-3
"""

from taskguard.analyzers.regex_extractor import RegexTemplate

_TEMPLATE = RegexTemplate(
    name="curl",
    patterns=[
        r"(?P<pct>\d+)\s+[\d.]+\w\s+\d+:\d+:\d+\s+(?P<spd>[\d.]+[KMGT]?B/s)",
    ],
    confidence_fn=lambda g: 1.0 if all(g.get(k) for k in ("pct", "spd")) else 0.3,
)
