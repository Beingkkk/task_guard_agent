"""System prompt and tool schema for StateAnalyzer.

Relates-to: FR-3
"""

from taskguard.llm.base import ToolDefinition

_STATE_SUMMARY_TOOL = ToolDefinition(
    name="state_summary",
    description="分析任务当前健康状态并返回结构化结论",
    input_schema={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["healthy", "stalled", "error", "unknown"],
                "description": "任务整体状态：健康、卡住、错误、无法判断",
            },
            "summary": {
                "type": "string",
                "description": "用一句话中文总结任务当前状态，说明理由",
            },
            "indicators": {
                "type": "object",
                "properties": {
                    "cpu_percent": {"type": ["number", "null"]},
                    "memory_percent": {"type": ["number", "null"]},
                    "process_status": {"type": ["string", "null"]},
                    "log_tail": {"type": "string"},
                    "recent_alerts": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "cpu_percent",
                    "memory_percent",
                    "process_status",
                    "log_tail",
                    "recent_alerts",
                ],
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "结论置信度，0-1 之间",
            },
        },
        "required": ["status", "summary", "indicators", "confidence"],
    },
)

STATE_SUMMARY_SYSTEM_PROMPT = """\
你是 TaskGuard 任务健康状态分析助手。用户正在监控一个长期运行的进程任务。

你的目标是判断该进程当前是否健康、是否卡住、是否异常，而不是计算下载进度。请根据提供的进程指标（CPU%、内存%、进程状态）和最近日志片段，判断任务当前整体状态，并给出一句可读的中文总结。

判断标准（注意：不要仅凭单一指标下结论）：
- healthy：进程运行正常，日志持续有输出或进程在等待 I/O；CPU 低但日志仍在更新是健康的（例如服务等待请求、数据库写入、等待网络、定时任务）
- stalled：进程还在，但**同时满足**以下多个条件：长时间无新的有效日志、CPU 持续接近 0%、也没有观察到任何状态/活动迹象；即“完全没有动静”
- error：日志中出现 ERROR/FATAL/Exception/Traceback，或进程状态为 exited/崩溃/退出码非 0
- unknown：信息不足，无法判断

重要提示：
1. 你的角色是任务健康状态监控助手，不是下载进度解析器。不要关注下载百分比、速度、ETA 等进度指标。
2. CPU 0% 不代表假死。很多正常任务会长时间 CPU 为 0 但仍在正常工作。
3. 判断 stalled 必须同时看：日志是否还在更新、CPU 是否持续为 0、是否有任何状态/活动迹象。
4. 如果日志里有正常的循环输出、心跳、I/O 活动，即使 CPU 很低，也应该是 healthy。
5. 如果只有少量日志且没有异常，但无法确定是否在推进，可以选 unknown 并说明理由。

输出要求：
1. 必须调用 state_summary 工具，返回 JSON 结构化数据
2. summary 字段用一句中文简洁说明当前状态和原因
3. indicators 中填入你实际看到的关键指标和最近几条日志（压缩成字符串）
4. confidence 表示你对自己判断的把握程度
"""

__all__ = ["STATE_SUMMARY_SYSTEM_PROMPT", "_STATE_SUMMARY_TOOL"]
