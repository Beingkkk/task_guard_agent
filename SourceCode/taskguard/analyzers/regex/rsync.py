"""rsync progress regex template.

Relates-to: FR-3
"""

from taskguard.analyzers.regex_extractor import RegexTemplate

_TEMPLATE = RegexTemplate(
    name="rsync",
    patterns=[
        r"(?P<pct>\d+)%\s+(?P<spd>[\d.]+[KMGT]?B/s)\s+(?P<eta>\d+:\d+:\d+)",
        r"(?P<pct>\d+)%\s+(?P<spd>[\d.]+[KMGT]?B/s)",
    ],
    confidence_fn=lambda g: (
        1.0
        if all(g.get(k) for k in ("pct", "spd", "eta"))
        else 0.6
        if all(g.get(k) for k in ("pct", "spd"))
        else 0.3
    ),
)
