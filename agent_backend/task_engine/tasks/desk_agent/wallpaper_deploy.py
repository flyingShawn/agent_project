"""
壁纸下发任务定义

文件功能：
    定义 desk-agent 的壁纸下发任务，将指定壁纸文件设置到目标客户端或部门。
    仅传递壁纸文件路径、目标客户端/部门等参数给 Qt 管理机执行。

关联文件：
    - task_engine/base.py: TaskDefinition 基类
"""
from __future__ import annotations

import httpx

from agent_backend.task_engine.base import (
    TaskDefinition,
    TaskParam,
    TaskParamOption,
    TaskParamType,
    TaskResult,
    TaskStep,
)


class WallpaperDeployTask(TaskDefinition):
    task_id = "wallpaper_deploy"
    name = "壁纸下发"
    description = "将指定壁纸设置到目标客户端或部门"
    icon = "image"
    category = "deploy"
    agent_type = "desk-agent"

    steps = [
        TaskStep(
            id="wallpaper_config",
            title="壁纸配置",
            description="填写需要下发的壁纸文件信息",
            params=[
                TaskParam(
                    key="wallpaper_file_path",
                    label="壁纸文件路径",
                    type=TaskParamType.FILE_PATH,
                    required=True,
                    placeholder="如：D:\\share\\wallpapers\\company_bg.jpg",
                    description="管理机上壁纸文件的完整路径",
                ),
                TaskParam(
                    key="wallpaper_style",
                    label="壁纸显示方式",
                    type=TaskParamType.SELECT,
                    required=True,
                    default="fill",
                    options=[
                        TaskParamOption(label="填充", value="fill"),
                        TaskParamOption(label="适应", value="fit"),
                        TaskParamOption(label="拉伸", value="stretch"),
                        TaskParamOption(label="居中", value="center"),
                        TaskParamOption(label="平铺", value="tile"),
                    ],
                ),
            ],
        ),
        TaskStep(
            id="select_targets",
            title="选择下发目标",
            description="选择需要设置壁纸的客户端或部门",
            params=[
                TaskParam(
                    key="target_type",
                    label="目标类型",
                    type=TaskParamType.SELECT,
                    required=True,
                    options=[
                        TaskParamOption(label="按客户端", value="client"),
                        TaskParamOption(label="按部门", value="department"),
                    ],
                ),
                TaskParam(
                    key="client_ids",
                    label="选择客户端",
                    type=TaskParamType.CLIENT_SELECTOR,
                    required=False,
                    description="当目标类型为「按客户端」时选择",
                ),
                TaskParam(
                    key="department_ids",
                    label="选择部门",
                    type=TaskParamType.DEPARTMENT_SELECTOR,
                    required=False,
                    description="当目标类型为「按部门」时选择",
                ),
            ],
        ),
    ]

    async def execute(self, params: dict) -> TaskResult:
        api_base = self._get_api_base_url()
        if not api_base:
            return TaskResult(success=False, message="未配置桌管服务 API 地址")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{api_base}/api/wallpaper/deploy",
                    json={
                        "wallpaper_file_path": params.get("wallpaper_file_path"),
                        "wallpaper_style": params.get("wallpaper_style", "fill"),
                        "target_type": params.get("target_type"),
                        "client_ids": params.get("client_ids", []),
                        "department_ids": params.get("department_ids", []),
                    },
                )
            if resp.status_code == 200:
                data = resp.json()
                return TaskResult(
                    success=True,
                    message="壁纸下发任务已提交",
                    data=data,
                    result_type="status_list",
                )
            return TaskResult(success=False, message=f"壁纸下发失败: {resp.text}")
        except httpx.TimeoutException:
            return TaskResult(success=False, message="下发请求超时，请检查桌管服务是否正常")
        except Exception as e:
            return TaskResult(success=False, message=f"下发请求异常: {e}")
