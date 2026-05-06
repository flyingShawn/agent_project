"""
文件推送任务定义

文件功能：
    定义 desk-agent 的文件推送任务，将管理机上的文件推送到指定客户端或部门。
    通过 FileBrowserModal 选择管理机上的文件获取完整路径，参数传给 Qt 管理机执行。

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


class FilePushTask(TaskDefinition):
    task_id = "file_push"
    name = "文件推送"
    description = "将管理机上的文件推送到目标客户端或部门"
    icon = "upload"
    category = "deploy"
    agent_type = "desk-agent"

    steps = [
        TaskStep(
            id="file_config",
            title="文件配置",
            description="选择需要推送的文件和目标路径",
            params=[
                TaskParam(
                    key="source_file_paths",
                    label="源文件",
                    type=TaskParamType.FILE_PATH,
                    required=True,
                    placeholder="点击浏览管理机上的文件，支持多选",
                    description="管理机上待推送的文件，可选择多个",
                    validation={"multiple": True},
                ),
                TaskParam(
                    key="target_dir",
                    label="目标目录",
                    type=TaskParamType.TEXT,
                    required=True,
                    placeholder="如：C:\\Program Files\\App",
                    description="客户端上的目标存放目录，手动输入",
                ),
                TaskParam(
                    key="conflict_policy",
                    label="重名处理策略",
                    type=TaskParamType.SELECT,
                    required=True,
                    default="overwrite",
                    options=[
                        TaskParamOption(label="覆盖已有文件", value="overwrite"),
                        TaskParamOption(label="自动重命名", value="rename"),
                        TaskParamOption(label="跳过不处理", value="skip"),
                    ],
                ),
            ],
        ),
        TaskStep(
            id="select_targets",
            title="选择推送目标",
            description="选择需要接收文件的客户端和/或部门，可同时选择",
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
                    placeholder="如：管理员正在向您推送文件",
                    description="仅在开启分发提示时生效",
                ),
            ],
        ),
        TaskStep(
            id="confirm",
            title="确认提交",
            description="确认推送信息并提交任务",
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
                    f"{api_base}/api/file/push",
                    json={
                        "source_file_paths": params.get("source_file_paths", []),
                        "target_dir": params.get("target_dir", ""),
                        "conflict_policy": params.get("conflict_policy", "overwrite"),
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
                    message="文件推送任务已提交",
                    data=data,
                    result_type="status_list",
                )
            return TaskResult(success=False, message=f"推送失败: {resp.text}")
        except httpx.TimeoutException:
            return TaskResult(success=False, message="推送请求超时，请检查桌管服务是否正常")
        except Exception as e:
            return TaskResult(success=False, message=f"推送请求异常: {e}")
