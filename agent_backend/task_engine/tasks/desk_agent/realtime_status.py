"""
获取实时状态任务定义

文件功能：
    定义 desk-agent 的获取实时状态任务，查询指定客户端的在线状态、
    系统信息等。参数传递给 Qt 管理机执行。

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


class RealtimeStatusTask(TaskDefinition):
    task_id = "realtime_status"
    name = "获取实时状态"
    description = "查询客户端在线状态、系统信息等实时数据"
    icon = "monitor"
    category = "query"
    agent_type = "desk-agent"

    steps = [
        TaskStep(
            id="select_targets",
            title="选择查询目标",
            description="选择需要查询状态的客户端和/或部门，可同时选择",
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
            id="query_config",
            title="查询配置",
            description="选择需要查询的状态信息",
            params=[
                TaskParam(
                    key="query_fields",
                    label="查询内容",
                    type=TaskParamType.MULTI_SELECT,
                    required=True,
                    default=["online_status", "system_info"],
                    options=[
                        TaskParamOption(label="在线状态", value="online_status"),
                        TaskParamOption(label="系统信息", value="system_info"),
                        TaskParamOption(label="资源使用率", value="resource_usage"),
                        TaskParamOption(label="网络状态", value="network_status"),
                        TaskParamOption(label="进程列表", value="process_list"),
                    ],
                ),
            ],
        ),
        TaskStep(
            id="confirm",
            title="确认提交",
            description="确认查询信息并提交任务",
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
                    f"{api_base}/api/status/query",
                    json={
                        "client_ids": params.get("client_ids", []),
                        "department_ids": params.get("department_ids", []),
                        "query_fields": params.get("query_fields", []),
                        "task_name": params.get("task_name", ""),
                    },
                )
            if resp.status_code == 200:
                data = resp.json()
                return TaskResult(
                    success=True,
                    message="状态查询完成",
                    data=data,
                    result_type="table",
                )
            return TaskResult(success=False, message=f"查询失败: {resp.text}")
        except httpx.TimeoutException:
            return TaskResult(success=False, message="查询超时，请检查桌管服务是否正常")
        except Exception as e:
            return TaskResult(success=False, message=f"查询异常: {e}")
