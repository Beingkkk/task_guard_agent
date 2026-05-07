"""Log source URI parsing for bash:// and file:// schemes.

Relates-to: FR-1
"""

from dataclasses import dataclass
from pathlib import PureWindowsPath


@dataclass(slots=True, frozen=True)
class LogSource:
    """Immutable log source descriptor."""

    type: str
    command: str | None = None
    path: str | None = None
    extensions: tuple[str, ...] = (".log", ".txt", ".out")

    @classmethod
    def from_uri(cls, uri: str) -> "LogSource":
        """Parse a log source URI.

        Supports:
            bash://<command>
            file://<absolute_path>

        Raises:
            ValueError: If the URI is malformed or the path is not absolute.
        """
        if "://" not in uri:
            raise ValueError(f"URI must contain scheme separator '://': {uri}")

        scheme, body = uri.split("://", 1)

        if scheme == "bash":
            cmd = body.strip()
            if not cmd:
                raise ValueError("bash:// command must not be empty")
            return cls(type="bash", command=cmd)

        if scheme == "file":
            path = body
            p = PureWindowsPath(path)
            # Accept both Windows absolute (C:\) and UNC (\\server\share) paths
            if not p.is_absolute():
                raise ValueError(f"file:// path must be absolute: {path}")
            return cls(type="file", path=path)

        raise ValueError(f"Unsupported scheme '{scheme}' in URI: {uri}")
