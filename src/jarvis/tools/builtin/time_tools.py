"""
内置工具 — 时间与日期
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from ..base import BaseTool, ToolParam, ToolResult


class GetTimeTool(BaseTool):
    """获取当前时间"""

    name        = "get_time"
    description = "获取当前日期和时间（支持时区）"
    category    = "utility"
    tags        = ["time", "date", "clock"]

    params = [
        ToolParam("timezone", str, "时区，如 Asia/Shanghai", required=False, default="Asia/Shanghai"),
        ToolParam("format",   str, "格式字符串",              required=False, default="%Y-%m-%d %H:%M:%S"),
    ]

    def execute(self, timezone: str = "Asia/Shanghai", format: str = "%Y-%m-%d %H:%M:%S") -> ToolResult:
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("Asia/Shanghai")

        now = datetime.datetime.now(tz)
        return ToolResult.ok(
            data={
                "datetime": now.strftime(format),
                "timezone": timezone,
                "weekday":  ["周一","周二","周三","周四","周五","周六","周日"][now.weekday()],
                "timestamp": int(now.timestamp()),
            },
            message=now.strftime(format),
        )


class GetCalendarTool(BaseTool):
    """获取指定月份的日历"""

    name        = "get_calendar"
    description = "获取某月的日历"
    category    = "utility"
    tags        = ["time", "calendar"]

    params = [
        ToolParam("year",  int, "年份（默认当前年）",  required=False, default=0),
        ToolParam("month", int, "月份（默认当前月）",  required=False, default=0),
    ]

    def execute(self, year: int = 0, month: int = 0) -> ToolResult:
        import calendar
        now = datetime.datetime.now()
        year  = year  or now.year
        month = month or now.month
        cal = calendar.month(year, month)
        return ToolResult.ok(data=cal, message=f"{year}年{month}月日历")
