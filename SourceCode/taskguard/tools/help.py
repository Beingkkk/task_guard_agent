"""Help tool implementation.

Relates-to: FR-4
"""

from typing import Any

from taskguard.tools.base import BaseTool, ToolResult

_HELP_TEXT = """\
可用命令：

  /watch <别名> --log <URI> [--pid <PID>]    注册监控任务
  /watch <别名> --revise [--log <URI>]        修改已有任务
  /unwatch <别名>                            注销监控任务
  /list                                      列出所有任务
  /status <别名>                             查询任务详情
  /progress <别名>                           查询最新进度
  /update                                    手动刷新全量收集
  /help                                      显示此帮助

你也可以用自然语言描述你的操作意图，例如：
  "帮我监控下载A，日志在 C:\\\\data\\\\dl.log"
  "现在有哪些任务在跑？"

  exit / quit / q                            退出 Agent
"""


class HelpTool(BaseTool):
    """Show help information."""

    name = "help"
    description = "Show help information"

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Return help text."""
        return ToolResult(ok=True, data=_HELP_TEXT)
