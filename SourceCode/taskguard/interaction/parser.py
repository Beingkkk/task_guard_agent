"""Command parser for /-prefixed shell commands.

Relates-to: FR-4
"""

from dataclasses import dataclass
from typing import Any


class ParseError(Exception):
    """Raised when a command cannot be parsed."""


@dataclass(slots=True)
class ParsedCommand:
    """Structured result of parsing a /-prefixed command."""

    tool_name: str
    params: dict[str, Any]


class CommandParser:
    """Parse /-prefixed commands into structured tool calls.

    CLI shell and Feishun Event Bot share the same parser.
    """

    _COMMAND_MAP: dict[str, str] = {
        "watch": "watch_task",
        "unwatch": "unwatch_task",
        "list": "list_tasks",
        "status": "query_status",
        "progress": "query_progress",
        "cleanup": "cleanup_exited",
        "update": "collect_all",
        "help": "help",
    }

    def parse(self, line: str) -> ParsedCommand:
        """Parse a /-prefixed command line.

        Args:
            line: Raw input line, e.g. "/watch 下载A --log bash://..."

        Raises:
            ParseError: If the command is unknown or malformed.
        """
        stripped = line.strip()
        if not stripped.startswith("/"):
            raise ParseError("Command must start with '/'")

        # Remove leading '/' and split
        content = stripped[1:].strip()
        tokens = content.split()

        if not tokens:
            raise ParseError("Empty command after '/'")

        # Map command name
        cmd_name = tokens[0]
        tool_name = self._COMMAND_MAP.get(cmd_name)
        if tool_name is None:
            raise ParseError(f"Unknown command: '{cmd_name}'")

        # Parse remaining tokens as --key value pairs
        params: dict[str, Any] = {}
        i = 1
        while i < len(tokens):
            token = tokens[i]
            if token.startswith("--"):
                key = token[2:]
                if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                    # Collect all consecutive non-flag tokens as the value
                    value_parts = [tokens[i + 1]]
                    j = i + 2
                    while j < len(tokens) and not tokens[j].startswith("--"):
                        value_parts.append(tokens[j])
                        j += 1
                    params[key] = " ".join(value_parts)
                    i = j
                else:
                    # Flag without explicit value
                    params[key] = "True"
                    i += 1
            else:
                # Positional argument: treat as alias if not already set
                if "alias" not in params:
                    params["alias"] = token
                i += 1

        return ParsedCommand(tool_name=tool_name, params=params)
