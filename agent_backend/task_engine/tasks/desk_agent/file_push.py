"""
文件推送任务定义

文件功能：
    定义 desk-agent 的文件推送任务，将管理机上的文件推送到指定客户端或部门。
    不上传文件，仅传递源文件路径、目标路径、重名策略等参数给 Qt 管理机执行。

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
            description="填写需要推送的文件信息",
            params=[
                TaskParam(
                    key="source_file_path",
                    label="源文件路径",
                    type=TaskParamType.FILE_PATH,
                    required=True,
                    placeholder="如：D:\\share\\update.exe",
                    description="管理机上待推送文件的完整路径",
                ),
                TaskParam(
                    key="target_file_path",
                    label="目标路径",
                    type=TaskParamType.FILE_PATH,
                    required=True,
                    placeholder="如：C:\\Program Files\\App\\update.exe",
                    description="客户端上的目标存放路径",
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
            description="选择需要接收文件的客户端或部门",
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
        TaskStep(
            id="confirm",
            title="确认推送",
            description="确认推送信息无误后提交",
            params=[
                TaskParam(
                    key="remark",
                    label="备注",
                    type=TaskParamType.TEXTAREA,
                    required=False,
                    placeholder="可选，填写推送说明",
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
                    f"{api_base}/api/file/push",
                    json={
                        "source_file_path": params.get("source_file_path"),
                        "target_file_path": params.get("target_file_path"),
                        "conflict_policy": params.get("conflict_policy", "overwrite"),
                        "target_type": params.get("target_type"),
                        "client_ids": params.get("client_ids", []),
                        "department_ids": params.get("department_ids", []),
                        "remark": params.get("remark", ""),
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
