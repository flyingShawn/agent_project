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
                    key="wallpaper_file_paths",
                    label="壁纸文件",
                    type=TaskParamType.FILE_PATH,
                    required=True,
                    placeholder="点击浏览管理机上的壁纸文件，支持多选",
                    description="管理机上的壁纸文件，可选择多个批量下发",
                    validation={"multiple": True},
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
            description="选择需要设置壁纸的客户端和/或部门，可同时选择",
            params=[
                TaskParam(
                    key="client_ids",
                    label="选择客户端",
                    type=TaskParamType.CLIENT_SELECTOR,
                    required=False,
                    options_api="client",
                    description="可选择特定客户端",
                ),
                TaskParam(
                    key="department_ids",
                    label="选择部门",
                    type=TaskParamType.DEPARTMENT_SELECTOR,
                    required=False,
                    options_api="department",
                    description="可选择整个部门，与客户端可同时选择",
                ),
            ],
        ),
        TaskStep(
            id="notification",
            title="分发提示",
            description="设置是否在客户端弹出提示",
            params=[
                TaskParam(
                    key="notify_enabled",
                    label="开启分发提示",
                    type=TaskParamType.BOOLEAN,
                    required=True,
                    default=False,
                ),
                TaskParam(
                    key="notify_message",
                    label="提示文字",
                    type=TaskParamType.TEXT,
                    required=False,
                    placeholder="如：管理员正在为您更换壁纸",
                    description="仅在开启分发提示时生效",
                ),
            ],
        ),
        TaskStep(
            id="confirm",
            title="确认提交",
            description="确认壁纸下发信息并提交任务",
            params=[
                TaskParam(
                    key="task_name",
                    label="任务名称",
                    type=TaskParamType.TEXT,
                    required=True,
                    placeholder="自动生成，可修改",
                ),
            ],
        ),
    ]

    async def validate_step(self, step_id: str, params: dict) -> dict:
        if step_id == "select_targets":
            client_ids = params.get("client_ids", [])
            department_ids = params.get("department_ids", [])
            if not client_ids and not department_ids:
                return {
                    "valid": False,
                    "errors": {
                        "client_ids": "请至少选择一个客户端或部门",
                    },
                }
            return {"valid": True, "errors": {}}
        return await super().validate_step(step_id, params)

    async def execute(self, params: dict) -> TaskResult:
        # 备用链路：desk-agent 当前主执行入口是浏览器本机 XFAgentBridge。
        # 这里保留给服务端转发模式或联调测试使用。
        api_base = self._get_api_base_url()
        if not api_base:
            return TaskResult(success=False, message="未配置桌管服务 API 地址")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{api_base}/api/wallpaper/deploy",
                    json={
                        "wallpaper_file_paths": params.get("wallpaper_file_paths", []),
                        "wallpaper_style": params.get("wallpaper_style", "fill"),
                        "client_ids": params.get("client_ids", []),
                        "department_ids": params.get("department_ids", []),
                        "notify_enabled": params.get("notify_enabled", False),
                        "notify_message": params.get("notify_message", ""),
                        "task_name": params.get("task_name", ""),
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
