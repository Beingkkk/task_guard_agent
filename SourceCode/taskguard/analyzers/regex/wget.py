"""wget progress regex template.

Relates-to: FR-3
"""

from taskguard.analyzers.regex_extractor import RegexTemplate

_TEMPLATE = RegexTemplate(
    name="wget",
    patterns=[
        r"(?P<pct>\d+)%\[.*?\]\s+[\d.]+\w+\s+(?P<spd>[\d.]+[KMGT]?B/s)\s+eta\s+(?P<eta>\S+)",
        r"(?P<pct>\d+)%\[.*?\]\s+(?P<spd>[\d.]+[KMGT]?B/s)",
        r"(?P<pct>\d+)%",
    ],
    confidence_fn=lambda g: (
        1.0
        if all(g.get(k) for k in ("pct", "spd", "eta"))
        else 0.6
        if all(g.get(k) for k in ("pct", "spd"))
        else 0.3
    ),
)
