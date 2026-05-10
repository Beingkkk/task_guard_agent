"""Restricted bash execution tool.

Relates-to: FR-4
"""

import asyncio
import shlex
from typing import Any

from taskguard.tools.base import BaseTool, ToolResult

# Whitelist of allowed command prefixes
_ALLOWED_PREFIXES = (
    "ps",
    "netstat",
    "tasklist",
    "wmic",
    "systeminfo",
    "ping",
    "tracert",
    "nslookup",
    "ipconfig",
    "hostname",
    "ver",
    "dir",
    "echo",
    "type",
    "findstr",
)

_MAX_OUTPUT_LINES = 50
_TIMEOUT_SECONDS = 10


class ExecBashTool(BaseTool):
    """Execute a restricted bash command and return its output."""

    name = "exec_bash"
    description = "Execute a restricted bash command (ps, netstat, tasklist, etc.)"

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        command = params.get("command", "").strip()
        if not command:
            return ToolResult(ok=False, error_code="empty_command", message="Command is empty")

        # Security: check whitelist
        first_token = shlex.split(command)[0].lower() if command else ""
        if not any(first_token.startswith(p) for p in _ALLOWED_PREFIXES):
            return ToolResult(
                ok=False,
                error_code="command_not_allowed",
                message=f"Command '{first_token}' is not in the allowed whitelist. "
                f"Allowed: {', '.join(_ALLOWED_PREFIXES)}",
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_SECONDS)
            output = stdout.decode("utf-8", errors="replace")
            lines = output.splitlines()
            if len(lines) > _MAX_OUTPUT_LINES:
                lines = lines[:_MAX_OUTPUT_LINES]
                lines.append(f"... ({len(output.splitlines()) - _MAX_OUTPUT_LINES} more lines)")
            return ToolResult(
                ok=True,
                data="\n".join(lines),
                message=f"Exit code: {proc.returncode}\n" + "\n".join(lines),
            )
        except TimeoutError:
            return ToolResult(
                ok=False,
                error_code="timeout",
                message=f"Command timed out after {_TIMEOUT_SECONDS}s",
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error_code="execution_error", message=str(exc))
