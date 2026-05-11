"""Log source path parsing.

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
    def parse(cls, input_str: str) -> "LogSource":
        """Parse a log source from a bare path or file:// URI.

        Supports single file or multiple files separated by semicolons:
            C:\\data\\dl.log
            C:\\logs\\a.log;C:\\logs\\b.log
            file://C:\\data\\dl.log         (legacy URI form)

        Raises:
            ValueError: If the path is empty, not absolute, or points to a directory.
        """
        raw = input_str.strip()
        if not raw:
            raise ValueError("Log path must not be empty")

        # Strip file:// prefix if present (legacy compatibility)
        if raw.lower().startswith("file://"):
            raw = raw[7:]

        # Reject other schemes
        if "://" in raw:
            scheme = raw.split("://", 1)[0]
            raise ValueError(
                f"Unsupported scheme '{scheme}://'. Only bare path or file:// is allowed."
            )

        paths = [p.strip() for p in raw.split(";") if p.strip()]
        if not paths:
            raise ValueError("Log path must specify at least one file")

        for path in paths:
            p = PureWindowsPath(path)
            if not p.is_absolute():
                raise ValueError(f"Path must be absolute: {path}")
            if path.endswith("\\") or path.endswith("/"):
                raise ValueError(f"Path must point to a file, not a directory: {path}")

        return cls(type="file", path=raw)

    @classmethod
    def from_uri(cls, uri: str) -> "LogSource":
        """Legacy alias for parse(). Kept for backward compatibility."""
        return cls.parse(uri)
