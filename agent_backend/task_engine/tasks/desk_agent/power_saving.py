"""
节能降耗设置任务定义

文件功能：
    定义 desk-agent 的节能降耗设置任务，配置客户端空闲待机、
    显示器关闭、定时关机等节能策略。参数传递给 Qt 管理机执行。

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


class PowerSavingTask(TaskDefinition):
    task_id = "power_saving"
    name = "节能降耗设置"
    description = "配置客户端节能策略：空闲超时、显示器关闭、定时关机等"
    icon = "leaf"
    category = "config"
    agent_type = "desk-agent"

    steps = [
        TaskStep(
            id="idle_policy",
            title="空闲策略",
            description="设置客户端空闲后的行为",
            params=[
                TaskParam(
                    key="idle_timeout_minutes",
                    label="空闲待机时间（分钟）",
                    type=TaskParamType.NUMBER,
                    required=True,
                    default=30,
                    placeholder="如：30",
                    validation={"min": 1, "max": 480},
                ),
                TaskParam(
                    key="display_off_minutes",
                    label="关闭显示器时间（分钟）",
                    type=TaskParamType.NUMBER,
                    required=True,
                    default=15,
                    validation={"min": 1, "max": 480},
                ),
            ],
        ),
        TaskStep(
            id="shutdown_policy",
            title="定时关机策略",
            description="设置晚间定时关机时间",
            params=[
                TaskParam(
                    key="auto_shutdown_enabled",
                    label="启用定时关机",
                    type=TaskParamType.BOOLEAN,
                    required=True,
                    default=True,
                ),
                TaskParam(
                    key="shutdown_time",
                    label="关机时间",
                    type=TaskParamType.TIME,
                    required=False,
                    default="22:00",
                    description="仅在启用定时关机时生效",
                ),
            ],
        ),
        TaskStep(
            id="select_targets",
            title="应用范围",
            description="选择需要应用节能策略的客户端和/或部门，可同时选择",
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
                    placeholder="如：管理员正在调整您的节能策略",
                    description="仅在开启分发提示时生效",
                ),
            ],
        ),
        TaskStep(
            id="confirm",
            title="确认提交",
            description="确认节能策略信息并提交任务",
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
                    f"{api_base}/api/power-saving/config",
                    json={
                        "idle_timeout_minutes": params.get("idle_timeout_minutes"),
                        "display_off_minutes": params.get("display_off_minutes"),
                        "auto_shutdown_enabled": params.get("auto_shutdown_enabled", True),
                        "shutdown_time": params.get("shutdown_time"),
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
                    message="节能降耗设置已提交",
                    data=data,
                    result_type="status_list",
                )
            return TaskResult(success=False, message=f"设置失败: {resp.text}")
        except httpx.TimeoutException:
            return TaskResult(success=False, message="请求超时，请检查桌管服务是否正常")
        except Exception as e:
            return TaskResult(success=False, message=f"请求异常: {e}")
