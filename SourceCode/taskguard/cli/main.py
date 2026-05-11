"""CLI entry point for TaskGuard.

Relates-to: FR-1
"""

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from taskguard.storage.task_store import TaskStore
from taskguard.tools import register_builtin_tools
from taskguard.tools.base import ToolRegistry, ToolResult

app = typer.Typer(name="taskguard", help="进程守护与智能监控 Agent", no_args_is_help=False)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """CLI entry point. Enter interactive shell when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        asyncio.run(_enter_shell())


def _data_dir() -> Path:
    raw = os.environ.get("TASKGUARD_DATA_DIR", "./data")
    return Path(raw).resolve()


async def _enter_shell() -> None:
    """Enter interactive shell with full agent environment."""
    from pathlib import Path

    from taskguard.cli.shell import InteractiveShell

    data = _data_dir()
    data.mkdir(parents=True, exist_ok=True)

    shell = await InteractiveShell.from_config(Path("config"), data)
    await shell.run()


def _format_list(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "No tasks registered."
    lines = [f"{'Alias':<20} {'Log':<30} {'PID':<10} {'Created At':<25}", "-" * 90]
    for t in tasks:
        pid_str = str(t.get("pid") or "-")
        log_str = str(t.get("log") or "-")[:28]
        lines.append(
            f"{t['alias']:<20} {log_str:<30} {pid_str:<10} {t['created_at']:<25}",
        )
    return "\n".join(lines)


def _exit_code_for(result: ToolResult) -> int:
    if result.ok:
        return 0
    mapping = {
        "alias_exists": 2,
        "alias_not_found": 3,
        "alias_managed_by_yaml": 2,
        "invalid_uri": 2,
        "invalid_pid": 2,
        "invalid_alias": 2,
    }
    return mapping.get(result.error_code or "", 1)


def _handle_result(
    result: ToolResult, success_formatter: Callable[[Any], str] | None = None
) -> None:
    if result.ok:
        if success_formatter and result.data is not None:
            typer.echo(success_formatter(result.data))
        return
    typer.secho(result.message or result.error_code or "Error", err=True, fg="red")
    raise typer.Exit(code=_exit_code_for(result))


@app.command()
def watch(
    alias: Annotated[str, typer.Argument(help="任务别名")],
    log: Annotated[str, typer.Option(help="日志文件路径（C:\\data\\dl.log 或多文件 C:\\a.log;C:\\b.log）")],
    pid: Annotated[int | None, typer.Option(help="进程 PID")] = None,
    tool: Annotated[str | None, typer.Option(help="显式标注工具类型（如 wget, rsync）")] = None,
) -> None:
    """注册监控任务（仅支持文件日志源；可省略 file:// 前缀）。"""
    data = _data_dir()
    data.mkdir(parents=True, exist_ok=True)
    store = TaskStore(data)
    register_builtin_tools(store)

    async def _run() -> None:
        await store.load()

        tool_obj = ToolRegistry.get("watch_task")
        params: dict[str, Any] = {"alias": alias, "log": log, "pid": pid, "_store": store}
        if tool is not None:
            params["tool_hint"] = tool
        result = await tool_obj.execute(params)
        _handle_result(result, lambda d: f"Registered task '{d.alias}'")

    asyncio.run(_run())


@app.command()
def unwatch(
    alias: Annotated[str, typer.Argument(help="任务别名")],
) -> None:
    """注销监控任务。"""
    data = _data_dir()
    store = TaskStore(data)
    register_builtin_tools(store)

    async def _run() -> None:
        await store.load()
        tool = ToolRegistry.get("unwatch_task")
        result = await tool.execute({"alias": alias, "_store": store})
        _handle_result(result, lambda d: f"Unregistered task '{d.alias}'")

    asyncio.run(_run())


@app.command(name="list")
def list_tasks() -> None:
    """列出所有监控任务。"""
    data = _data_dir()
    store = TaskStore(data)
    register_builtin_tools(store)

    async def _run() -> None:
        await store.load()
        tool = ToolRegistry.get("list_tasks")
        result = await tool.execute({"_store": store})
        _handle_result(result, _format_list)

    asyncio.run(_run())


@app.command()
def status(
    alias: Annotated[str, typer.Argument(help="任务别名")],
) -> None:
    """查询任务详情。"""
    data = _data_dir()
    store = TaskStore(data)
    register_builtin_tools(store)

    async def _run() -> None:
        await store.load()
        tool = ToolRegistry.get("query_status")
        result = await tool.execute({"alias": alias, "_store": store})
        _handle_result(result, lambda d: json.dumps(d, indent=2, ensure_ascii=False))

    asyncio.run(_run())


if __name__ == "__main__":
    app()
