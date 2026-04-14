"""
数据导出工具模块

文件功能：
    定义export_data Tool，将查询数据导出为Excel或CSV文件供用户下载。
    作为LangGraph Tool注册，由LLM通过Tool Calling自主调用。

在系统架构中的定位：
    位于Agent工具层，为Agent提供数据导出能力。
    导出的文件通过临时目录存储，前端通过下载API获取。

主要使用场景：
    - 用户问"把这些数据导出Excel"时，生成xlsx文件
    - 用户问"下载设备清单"时，生成csv文件
    - 用户需要离线分析或汇报查询结果时

核心函数：
    - export_data: LangGraph Tool，接收数据和格式，生成文件并返回下载链接
    - _export_csv: 将数据写入CSV文件（UTF-8 BOM编码，兼容Excel）
    - _export_xlsx: 将数据写入Excel文件（依赖openpyxl）
    - _cleanup_old_files: 清理过期导出文件（TTL 2小时）

专有技术说明：
    - 文件存储在系统临时目录的desk_agent_exports子目录
    - 文件名格式：{安全化filename}_{8位UUID}.{format}
    - CSV使用utf-8-sig编码（带BOM），确保Excel正确识别中文
    - openpyxl可选依赖：未安装时自动降级为CSV格式
    - 过期文件自动清理：每次导出时清理超过2小时的旧文件
    - 数据行数限制：最多导出10000行，超出截断

安全注意事项：
    - 文件名安全化：仅保留字母数字和_-字符，防止路径遍历
    - 下载API路径校验：防止通过../等路径访问非导出目录
    - 文件大小限制：_MAX_ROWS=10000防止生成超大文件

关联文件：
    - agent_backend/agent/tools/__init__.py: ALL_TOOLS注册
    - agent_backend/api/v1/export.py: 文件下载API端点
    - agent_backend/agent/stream.py: SSE export事件发送
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_EXPORT_DIR = os.path.join(tempfile.gettempdir(), "desk_agent_exports")
_MAX_ROWS = 10000
_FILE_TTL_HOURS = 2

try:
    import openpyxl
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False


def _cleanup_old_files() -> None:
    """
    清理过期的导出文件。

    遍历导出目录，删除修改时间超过_FILE_TTL_HOURS(2小时)的文件。
    异常静默处理，不影响主流程。
    """
    try:
        if not os.path.exists(_EXPORT_DIR):
            return
        now = datetime.now().timestamp()
        for fname in os.listdir(_EXPORT_DIR):
            fpath = os.path.join(_EXPORT_DIR, fname)
            if os.path.isfile(fpath):
                mtime = os.path.getmtime(fpath)
                if (now - mtime) > _FILE_TTL_HOURS * 3600:
                    os.remove(fpath)
    except Exception:
        pass


def _export_csv(columns: list[str], rows: list[dict], filepath: str) -> None:
    """
    将数据导出为CSV文件。

    使用utf-8-sig编码（带BOM），确保Excel打开时正确识别中文。
    数据行数超过_MAX_ROWS时截断。

    参数：
        columns: 列名列表
        rows: 数据行列表
        filepath: 输出文件路径
    """
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows[:_MAX_ROWS])


def _export_xlsx(columns: list[str], rows: list[dict], filepath: str) -> None:
    """
    将数据导出为Excel文件。

    依赖openpyxl库，未安装时抛出RuntimeError。
    数据行数超过_MAX_ROWS时截断。

    参数：
        columns: 列名列表
        rows: 数据行列表
        filepath: 输出文件路径

    异常：
        RuntimeError: openpyxl未安装
    """
    if not _HAS_OPENPYXL:
        raise RuntimeError("openpyxl未安装，无法导出xlsx格式。请运行: pip install openpyxl")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(columns)
    for row in rows[:_MAX_ROWS]:
        ws.append([row.get(col, "") for col in columns])
    wb.save(filepath)


class ExportInput(BaseModel):
    """数据导出工具入参模型"""
    data: str = Field(description="JSON格式的数据，必须包含columns(列名列表)和rows(数据行列表)")
    filename: str = Field(default="export", description="导出文件名（不含扩展名）")
    format: str = Field(default="xlsx", description="导出格式：xlsx 或 csv")


@tool(args_schema=ExportInput)
def export_data(data: str, filename: str = "export", format: str = "xlsx") -> str:
    """
    将数据导出为Excel或CSV文件供用户下载。
    当用户要求导出、下载、保存查询结果时使用此工具。
    导出成功后会返回下载链接，用户可点击下载。

    参数：
        data: JSON格式数据，如 {"columns": ["部门","数量"], "rows": [{"部门":"研发部","数量":50}]}
        filename: 导出文件名（不含扩展名）
        format: 导出格式：xlsx 或 csv

    返回：
        str: JSON格式字符串，包含download_url/filename/row_count/format字段；
             导出失败时包含error和hint字段
    """
    logger.info(f"\n[export_data] 导出数据: filename={filename}, format={format}")

    try:
        valid_formats = {"xlsx", "csv"}
        if format not in valid_formats:
            return json.dumps({
                "error": f"不支持的导出格式: {format}",
                "hint": f"支持的格式: {', '.join(sorted(valid_formats))}",
            }, ensure_ascii=False)

        if format == "xlsx" and not _HAS_OPENPYXL:
            format = "csv"
            logger.info(f"\n[export_data] openpyxl未安装，自动切换为csv格式")

        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError as e:
            return json.dumps({
                "error": f"data参数JSON解析失败: {e}",
                "hint": "请确保data是有效的JSON字符串",
            }, ensure_ascii=False)

        columns = parsed_data.get("columns", [])
        rows = parsed_data.get("rows", [])

        if not columns or not rows:
            return json.dumps({
                "error": "数据为空，无法导出",
                "hint": "data必须包含非空的columns和rows",
            }, ensure_ascii=False)

        if len(rows) > _MAX_ROWS:
            logger.warning(f"\n[export_data] 数据行数{len(rows)}超过限制{_MAX_ROWS}，将截断")

        _cleanup_old_files()

        os.makedirs(_EXPORT_DIR, exist_ok=True)

        safe_name = "".join(c for c in filename if c.isalnum() or c in "_-") or "export"
        file_id = uuid.uuid4().hex[:8]
        full_filename = f"{safe_name}_{file_id}.{format}"
        filepath = os.path.join(_EXPORT_DIR, full_filename)

        if format == "csv":
            _export_csv(columns, rows, filepath)
        else:
            _export_xlsx(columns, rows, filepath)

        download_url = f"/api/v1/export/download/{full_filename}"

        logger.info(f"\n[export_data] 导出成功: {full_filename}, 行数: {min(len(rows), _MAX_ROWS)}")

        return json.dumps({
            "download_url": download_url,
            "filename": full_filename,
            "row_count": min(len(rows), _MAX_ROWS),
            "format": format,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[export_data] 异常: {type(e).__name__}: {e}")
        return json.dumps({
            "error": f"导出失败: {type(e).__name__}: {e}",
        }, ensure_ascii=False)
