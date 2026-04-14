"""
图表生成工具模块

文件功能：
    定义generate_chart Tool，根据数据生成ECharts图表配置。
    作为LangGraph Tool注册，由LLM通过Tool Calling自主调用。

在系统架构中的定位：
    位于Agent工具层，为Agent提供数据可视化能力。
    生成的ECharts配置JSON通过SSE chart事件发送给前端渲染。

主要使用场景：
    - 用户问"各部门设备数量对比"时，生成柱状图
    - 用户问"告警趋势"时，生成折线图
    - 用户问"设备类型占比"时，生成饼图

核心函数：
    - generate_chart: LangGraph Tool，接收图表类型和数据，返回ECharts配置JSON
    - _build_bar_option: 构建柱状图ECharts配置
    - _build_line_option: 构建折线图ECharts配置
    - _build_pie_option: 构建饼图ECharts配置

专有技术说明：
    - 采用ECharts配置JSON方案（非图片生成），前端渲染交互性更好
    - 支持三种图表类型：bar(柱状图)、line(折线图)、pie(饼图)
    - 自动推断Y轴字段：未指定y_field时，自动选取非X轴的所有列
    - 饼图自动推断名称字段和数值字段：默认取columns[0]和columns[1]
    - 内置10色配色方案，多系列自动循环分配颜色

前端配合说明：
    - 前端需监听SSE chart事件，获取echarts_option字段
    - 使用ECharts库渲染option配置

关联文件：
    - agent_backend/agent/tools/__init__.py: ALL_TOOLS注册
    - agent_backend/agent/prompts.py: SYSTEM_PROMPT中图表工具决策规则
    - agent_backend/agent/nodes.py: tool_result_node收集chart_configs
    - agent_backend/agent/stream.py: SSE chart事件发送
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_CHART_COLORS = [
    "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
    "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#48b8d0",
]


def _build_bar_option(title: str, data: dict, x_field: str, y_field: str | None) -> dict:
    """
    构建柱状图ECharts配置。

    参数：
        title: 图表标题
        data: 包含columns和rows的数据字典
        x_field: X轴分类字段名
        y_field: Y轴数值字段名，为None时自动选取非X轴的所有列

    返回：
        dict: ECharts option配置字典
    """
    columns = data.get("columns", [])
    rows = data.get("rows", [])

    x_idx = columns.index(x_field) if x_field in columns else 0
    x_data = [str(row.get(x_field, "")) for row in rows]

    y_fields = [y_field] if y_field else [c for c in columns if c != x_field]
    series_list = []
    for i, yf in enumerate(y_fields):
        y_data = [row.get(yf, 0) for row in rows]
        series_list.append({
            "name": yf,
            "type": "bar",
            "data": y_data,
            "itemStyle": {"color": _CHART_COLORS[i % len(_CHART_COLORS)]},
        })

    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0},
        "xAxis": {"type": "category", "data": x_data, "axisLabel": {"rotate": 30}},
        "yAxis": {"type": "value"},
        "series": series_list,
    }


def _build_line_option(title: str, data: dict, x_field: str, y_field: str | None) -> dict:
    """
    构建折线图ECharts配置。

    参数：
        title: 图表标题
        data: 包含columns和rows的数据字典
        x_field: X轴分类字段名
        y_field: Y轴数值字段名，为None时自动选取非X轴的所有列

    返回：
        dict: ECharts option配置字典
    """
    columns = data.get("columns", [])
    rows = data.get("rows", [])

    x_idx = columns.index(x_field) if x_field in columns else 0
    x_data = [str(row.get(x_field, "")) for row in rows]

    y_fields = [y_field] if y_field else [c for c in columns if c != x_field]
    series_list = []
    for i, yf in enumerate(y_fields):
        y_data = [row.get(yf, 0) for row in rows]
        series_list.append({
            "name": yf,
            "type": "line",
            "data": y_data,
            "smooth": True,
            "itemStyle": {"color": _CHART_COLORS[i % len(_CHART_COLORS)]},
        })

    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0},
        "xAxis": {"type": "category", "data": x_data, "boundaryGap": False},
        "yAxis": {"type": "value"},
        "series": series_list,
    }


def _build_pie_option(title: str, data: dict, x_field: str, y_field: str | None) -> dict:
    """
    构建饼图ECharts配置。

    参数：
        title: 图表标题
        data: 包含columns和rows的数据字典
        x_field: 名称字段名，为None时默认取columns[0]
        y_field: 数值字段名，为None时默认取columns[1]

    返回：
        dict: ECharts option配置字典
    """
    columns = data.get("columns", [])
    rows = data.get("rows", [])

    name_field = x_field or (columns[0] if columns else "name")
    value_field = y_field or (columns[1] if len(columns) > 1 else "value")

    pie_data = []
    for row in rows:
        pie_data.append({
            "name": str(row.get(name_field, "")),
            "value": row.get(value_field, 0),
        })

    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"orient": "vertical", "left": "left", "top": "middle"},
        "series": [{
            "type": "pie",
            "radius": ["40%", "70%"],
            "avoidLabelOverlap": True,
            "itemStyle": {"borderRadius": 6, "borderColor": "#fff", "borderWidth": 2},
            "label": {"show": True, "formatter": "{b}: {d}%"},
            "data": pie_data,
        }],
    }


class ChartInput(BaseModel):
    """图表生成工具入参模型"""
    chart_type: str = Field(description="图表类型：bar(柱状图)、line(折线图)、pie(饼图)")
    title: str = Field(description="图表标题")
    data: str = Field(description="JSON格式的数据，必须包含columns(列名列表)和rows(数据行列表)")
    x_field: str | None = Field(default=None, description="X轴/分类字段名，饼图时为名称字段")
    y_field: str | None = Field(default=None, description="Y轴/数值字段名，饼图时为数值字段；为空时自动选取非X轴的数值列")


@tool(args_schema=ChartInput)
def generate_chart(chart_type: str, title: str, data: str,
                   x_field: str | None = None, y_field: str | None = None) -> str:
    """
    根据数据生成图表配置。
    当用户需要可视化展示数据对比、趋势、占比时使用此工具。
    支持柱状图(bar)、折线图(line)、饼图(pie)。
    生成的图表配置将发送给前端渲染展示。

    参数：
        chart_type: 图表类型：bar(柱状图)、line(折线图)、pie(饼图)
        title: 图表标题
        data: JSON格式数据，如 {"columns": ["部门","数量"], "rows": [{"部门":"研发部","数量":50}]}
        x_field: X轴/分类字段名
        y_field: Y轴/数值字段名

    返回：
        str: JSON格式字符串，包含echarts_option和chart_type字段；
             生成失败时包含error和hint字段
    """
    logger.info(f"\n[generate_chart] 生成图表: type={chart_type}, title={title}")

    try:
        valid_types = {"bar", "line", "pie"}
        if chart_type not in valid_types:
            return json.dumps({
                "error": f"不支持的图表类型: {chart_type}",
                "hint": f"支持的类型: {', '.join(sorted(valid_types))}",
            }, ensure_ascii=False)

        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError as e:
            return json.dumps({
                "error": f"data参数JSON解析失败: {e}",
                "hint": "请确保data是有效的JSON字符串，格式: {\"columns\": [...], \"rows\": [...]}",
            }, ensure_ascii=False)

        if not isinstance(parsed_data, dict):
            return json.dumps({"error": "data参数必须是JSON对象"}, ensure_ascii=False)

        columns = parsed_data.get("columns", [])
        rows = parsed_data.get("rows", [])

        if not columns or not rows:
            return json.dumps({
                "error": "数据为空",
                "hint": "data必须包含非空的columns和rows",
            }, ensure_ascii=False)

        resolved_x = x_field or (columns[0] if columns else None)
        if not resolved_x:
            return json.dumps({"error": "无法确定X轴字段，请指定x_field"}, ensure_ascii=False)

        builders = {
            "bar": _build_bar_option,
            "line": _build_line_option,
            "pie": _build_pie_option,
        }

        option = builders[chart_type](title, parsed_data, resolved_x, y_field)

        logger.info(f"\n[generate_chart] 图表配置生成成功: {chart_type}, 数据行数: {len(rows)}")
        return json.dumps({
            "chart_type": chart_type,
            "echarts_option": option,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[generate_chart] 异常: {type(e).__name__}: {e}")
        return json.dumps({
            "error": f"图表生成失败: {type(e).__name__}: {e}",
        }, ensure_ascii=False)
