"""
日志格式器
"""
import json
from .core import LogEntry, LogLevel


# 控制台颜色码
_COLORS = {
    LogLevel.DEBUG:    "\033[36m",   # Cyan
    LogLevel.INFO:     "\033[32m",   # Green
    LogLevel.WARNING:  "\033[33m",   # Yellow
    LogLevel.ERROR:    "\033[31m",   # Red
    LogLevel.CRITICAL: "\033[35m",   # Magenta
}
_RESET = "\033[0m"
_BOLD  = "\033[1m"

# 组件名对应的颜色（让不同模块颜色有区分）
_COMPONENT_COLORS = [
    "\033[96m",   # 亮青
    "\033[93m",   # 亮黄
    "\033[94m",   # 蓝
    "\033[92m",   # 亮绿
    "\033[95m",   # 亮紫
]
_component_color_map: dict = {}


def _component_color(name: str) -> str:
    if name not in _component_color_map:
        idx = len(_component_color_map) % len(_COMPONENT_COLORS)
        _component_color_map[name] = _COMPONENT_COLORS[idx]
    return _component_color_map[name]


class ConsoleFormatter:
    """
    控制台格式器 — 人类友好的彩色输出
    
    输出样例:
      11:02:33.421 [ INFO   ] [web_search] Tavily 返回 8 条结果 (trace:a1b2c3d4)
    """

    def __init__(self, use_color: bool = True, show_trace: bool = True):
        self.use_color = use_color
        self.show_trace = show_trace

    def __call__(self, entry: LogEntry) -> str:
        time_str  = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]
        level_str = f"[{entry.level.value:8}]"
        comp_str  = f"[{entry.component}]" if entry.component else ""

        if self.use_color:
            level_color = _COLORS.get(entry.level, "")
            comp_color  = _component_color(entry.component) if entry.component else ""
            level_str   = f"{_BOLD}{level_color}{level_str}{_RESET}"
            comp_str    = f"{comp_color}{comp_str}{_RESET}" if comp_str else ""

        parts = [time_str, level_str]
        if comp_str:
            parts.append(comp_str)
        parts.append(entry.message)

        if self.show_trace and entry.trace_id:
            parts.append(f"\033[2m(trace:{entry.trace_id}){_RESET}" if self.use_color
                         else f"(trace:{entry.trace_id})")

        line = " ".join(parts)

        # 附加上下文 key=value
        if entry.context:
            ctx_pairs = " ".join(f"{k}={v}" for k, v in entry.context.items())
            dim = "\033[2m" if self.use_color else ""
            line += f"\n  {dim}↳ {ctx_pairs}{_RESET if self.use_color else ''}"

        return line


class JSONFormatter:
    """
    JSON 格式器 — 方便机器解析、ELK/Grafana 接入
    
    每行一个 JSON 对象（NDJSON）
    """

    def __init__(self, indent: int = 0):
        self.indent = indent or None   # None → 单行，>0 → 缩进美化

    def __call__(self, entry: LogEntry) -> str:
        return json.dumps(entry.to_dict(), ensure_ascii=False, indent=self.indent)


class SimpleFormatter:
    """最简格式器（无颜色，适合重定向到文件）"""

    def __call__(self, entry: LogEntry) -> str:
        time_str  = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        comp_str  = f"[{entry.component}] " if entry.component else ""
        return f"{time_str} {entry.level.value:8} {comp_str}{entry.message}"
