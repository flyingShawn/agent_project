"""
时间工具模块

文件功能：
    定义get_current_time Tool，提供当前日期时间和常用日期范围查询。
    作为LangGraph Tool注册，由LLM通过Tool Calling自主调用。

在系统架构中的定位：
    位于Agent工具层，为Agent提供环境感知能力（当前时间）。
    解决LLM不知道当前时间导致SQL日期条件永远出错的致命问题。

主要使用场景：
    - 用户问"今天有多少台设备在线"时，LLM先调用此工具获取当前日期
    - 用户问"本月告警数量"时，LLM获取本月起止日期用于SQL查询
    - 用户问"最近7天在线率"时，LLM获取日期范围用于构建WHERE条件

核心函数：
    - get_current_time: LangGraph Tool，返回当前日期、时间、星期、常用日期范围
    - _month_range: 辅助函数，计算指定日期所在月份的起止日期

专有技术说明：
    - 纯Python datetime实现，无外部依赖
    - 返回JSON格式，包含today/yesterday/本周/本月/上月/本年/最近N天等完整日期范围
    - LLM获取时间后，在后续sql_query调用中将日期信息注入SQL生成Prompt

关联文件：
    - agent_backend/agent/tools/__init__.py: ALL_TOOLS注册
    - agent_backend/agent/prompts.py: SYSTEM_PROMPT中时间工具决策规则
    - agent_backend/agent/nodes.py: tool_result_node收集time_results
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_WEEKDAY_MAP = {
    0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四",
    4: "星期五", 5: "星期六", 6: "星期日",
}


class TimeToolInput(BaseModel):
    """时间工具入参模型（无参数，调用即返回当前时间）"""
    pass


def _month_range(dt: datetime) -> tuple[str, str]:
    """
    计算指定日期所在月份的起止日期。

    参数：
        dt: 目标日期

    返回：
        tuple[str, str]: (月初日期, 月末日期)，格式为 YYYY-MM-DD
    """
    first = dt.replace(day=1)
    if dt.month == 12:
        last = dt.replace(year=dt.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
    return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")


@tool(args_schema=TimeToolInput)
def get_current_time() -> str:
    """
    获取当前日期和时间信息。
    当用户问题涉及"今天"、"昨天"、"本月"、"本周"、"最近N天"、"今年"等时间相关表述时，
    必须先调用此工具获取准确时间，再基于返回结果生成SQL查询或回答问题。

    返回：
        str: JSON格式字符串，包含以下字段：
            - current_date: 当前日期 (YYYY-MM-DD)
            - current_datetime: 当前日期时间 (YYYY-MM-DD HH:MM:SS)
            - day_of_week: 星期几（中文）
            - today/yesterday/tomorrow: 相对日期
            - today_start/today_end: 今日起止时间
            - this_week_start/this_week_end: 本周起止日期
            - this_month_start/this_month_end: 本月起止日期
            - last_month_start/last_month_end: 上月起止日期
            - this_year_start/this_year_end: 本年起止日期
            - recent_7/30/90_days_start: 最近N天起始日期
    """
    logger.info(f"\n[get_current_time] 获取当前时间")

    try:
        now = datetime.now()
        today = now.date()

        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        this_month_start, this_month_end = _month_range(now)

        this_year_start = f"{now.year}-01-01"
        this_year_end = f"{now.year}-12-31"

        weekday_iso = now.weekday()
        monday_offset = weekday_iso
        this_week_monday = today - timedelta(days=monday_offset)
        this_week_sunday = this_week_monday + timedelta(days=6)

        recent_7_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
        recent_30_start = (today - timedelta(days=29)).strftime("%Y-%m-%d")
        recent_90_start = (today - timedelta(days=89)).strftime("%Y-%m-%d")

        last_month = now.month - 1 if now.month > 1 else 12
        last_month_year = now.year if now.month > 1 else now.year - 1
        last_month_dt = now.replace(year=last_month_year, month=last_month, day=1)
        last_month_start, last_month_end = _month_range(last_month_dt)

        result: dict[str, Any] = {
            "current_date": today.strftime("%Y-%m-%d"),
            "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "current_time": now.strftime("%H:%M:%S"),
            "day_of_week": _WEEKDAY_MAP[weekday_iso],
            "today": today.strftime("%Y-%m-%d"),
            "yesterday": yesterday.strftime("%Y-%m-%d"),
            "tomorrow": tomorrow.strftime("%Y-%m-%d"),
            "today_start": f"{today.strftime('%Y-%m-%d')} 00:00:00",
            "today_end": f"{today.strftime('%Y-%m-%d')} 23:59:59",
            "this_week_start": this_week_monday.strftime("%Y-%m-%d"),
            "this_week_end": this_week_sunday.strftime("%Y-%m-%d"),
            "this_month_start": this_month_start,
            "this_month_end": this_month_end,
            "last_month_start": last_month_start,
            "last_month_end": last_month_end,
            "this_year_start": this_year_start,
            "this_year_end": this_year_end,
            "recent_7_days_start": recent_7_start,
            "recent_30_days_start": recent_30_start,
            "recent_90_days_start": recent_90_start,
        }

        logger.info(f"\n[get_current_time] 当前日期: {result['current_date']}, {result['day_of_week']}")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[get_current_time] 异常: {type(e).__name__}: {e}")
        return json.dumps({"error": f"获取时间失败: {type(e).__name__}: {e}"}, ensure_ascii=False)
