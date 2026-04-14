"""
文件导出下载API端点

文件功能：
    提供导出文件的下载接口，供前端通过URL下载export_data工具生成的文件。

在系统架构中的定位：
    位于API层，是export_data工具生成文件后的下载入口。
    与export_tool.py配合，完成"生成文件→返回下载链接→用户下载"的完整流程。

主要使用场景：
    - export_data工具返回download_url后，前端展示下载链接
    - 用户点击下载链接，浏览器请求此API获取文件

核心端点：
    - GET /api/v1/export/download/{filename}: 下载指定导出文件

安全注意事项：
    - 路径遍历防护：校验realpath是否在导出目录内，防止../等路径攻击
    - 文件存在性检查：文件不存在或已过期返回404
    - Content-Type自动识别：根据扩展名设置csv或xlsx的MIME类型

关联文件：
    - agent_backend/agent/tools/export_tool.py: 生成导出文件并返回下载URL
    - agent_backend/api/routes.py: 路由注册
"""
from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])

_EXPORT_DIR = os.path.join(tempfile.gettempdir(), "desk_agent_exports")


@router.get("/export/download/{filename}")
def download_export(filename: str) -> FileResponse:
    """
    下载导出文件。

    根据文件名从导出目录返回文件响应。
    文件由export_data工具生成，存储在系统临时目录。

    参数：
        filename: 导出文件名（含扩展名），如 export_a1b2c3d4.xlsx

    返回：
        FileResponse: 文件下载响应

    异常：
        HTTPException 404: 文件不存在或已过期（TTL 2小时后被自动清理）
        HTTPException 400: 非法文件路径（路径遍历攻击防护）
    """
    filepath = os.path.join(_EXPORT_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件不存在或已过期")

    real_dir = os.path.realpath(os.path.dirname(filepath))
    expected_dir = os.path.realpath(_EXPORT_DIR)
    if not real_dir.startswith(expected_dir):
        raise HTTPException(status_code=400, detail="非法文件路径")

    ext = os.path.splitext(filename)[1].lower()
    media_type = "text/csv" if ext == ".csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    logger.info(f"\n[download_export] 下载文件: {filename}")
    return FileResponse(
        path=filepath,
        media_type=media_type,
        filename=filename,
    )
