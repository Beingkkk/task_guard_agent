"""CLI entry point."""

import typer

app = typer.Typer(name="taskguard", help="进程守护与智能监控 Agent")


@app.command()
def watch(
    alias: str = typer.Argument(..., help="任务别名"),
    pid: int | None = typer.Option(None, help="进程 PID"),
    log: str = typer.Option(..., help="日志源路径（file:// 或 bash://）"),
) -> None:
    """注册监控任务。"""
    typer.echo(f"TODO: watch {alias} pid={pid} log={log}")


@app.command()
def unwatch(alias: str = typer.Argument(..., help="任务别名")) -> None:
    """注销监控任务。"""
    typer.echo(f"TODO: unwatch {alias}")


@app.command()
def list() -> None:
    """列出所有监控任务。"""
    typer.echo("TODO: list tasks")


@app.command()
def status(alias: str = typer.Argument(..., help="任务别名")) -> None:
    """查询任务详情。"""
    typer.echo(f"TODO: status {alias}")


if __name__ == "__main__":
    app()
