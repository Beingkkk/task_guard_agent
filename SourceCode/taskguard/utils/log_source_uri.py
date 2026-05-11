"""Log source URI parsing for file:// scheme.

Relates-to: FR-1
"""

from dataclasses import dataclass
from pathlib import PureWindowsPath


@dataclass(slots=True, frozen=True)
class LogSource:
    """Immutable log source descriptor (file-only)."""

    type: str  # always "file"
    path: str | None = None  # semicolon-separated file paths
    extensions: tuple[str, ...] = (".log", ".txt", ".out")

    @property
    def paths(self) -> list[str]:
        """Return individual file paths from semicolon-separated string."""
        if not self.path:
            return []
        return [p.strip() for p in self.path.split(";") if p.strip()]

    @classmethod
    def from_uri(cls, uri: str) -> "LogSource":
        """Parse a file:// URI.

        Supports single file or multiple files separated by semicolons:
            file://C:\\data\\dl.log
            file://C:\\logs\\a.log;C:\\logs\\b.log

        Raises:
            ValueError: If the URI is malformed, path is not absolute,
                        or path points to a directory.
        """
        if "://" not in uri:
            raise ValueError(f"URI must contain scheme separator '://': {uri}")

        scheme, body = uri.split("://", 1)

        if scheme != "file":
            raise ValueError(
                f"Unsupported scheme '{scheme}'. Only file:// is supported: {uri}"
            )

        raw_paths = body
        paths = [p.strip() for p in raw_paths.split(";") if p.strip()]
        if not paths:
            raise ValueError("file:// must specify at least one file path")

        for path in paths:
            p = PureWindowsPath(path)
            if not p.is_absolute():
                raise ValueError(f"file:// path must be absolute: {path}")
            # On Windows, check if path looks like a directory (ends with separator)
            if path.endswith("\\") or path.endswith("/"):
                raise ValueError(
                    f"file:// must point to a file, not a directory: {path}"
                )

        return cls(type="file", path=raw_paths)
