"""aria2 progress regex template.

Relates-to: FR-3
"""

from taskguard.analyzers.regex_extractor import RegexTemplate

_TEMPLATE = RegexTemplate(
    name="aria2",
    patterns=[
        r"\[#[\w]+\s+[\d.]+\w+\s+\((?P<pct>\d+)%\)\s+(?P<spd>[\d.]+[KMGT]?B/s)",
        r"\((?P<pct>\d+)%\)",
    ],
    confidence_fn=lambda g: 1.0 if all(g.get(k) for k in ("pct", "spd")) else 0.3,
)
