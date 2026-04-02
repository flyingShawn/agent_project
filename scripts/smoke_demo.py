"""
冒烟测试演示脚本

文件目的：
    - 快速验证项目核心功能是否正常
    - 演示API调用方式
    - 用于开发和部署后的快速检查

核心功能：
    1. 加载schema元数据
    2. 测试健康检查API
    3. 测试元数据查询API
    4. 测试SQL生成API

测试流程：
    1. 加载schema_metadata.yaml
    2. 打印schema摘要信息
    3. 调用 /api/v1/health
    4. 调用 /api/v1/metadata/summary
    5. 调用 /api/v1/sql/generate

运行方式：
    python scripts/smoke_demo.py

使用场景：
    - 开发环境快速验证
    - 部署后健康检查
    - API调用示例

相关文件：
    - agent_backend/main.py: 应用入口
    - agent_backend/core/config_loader.py: 配置加载
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from agent_backend.core.config_loader import get_schema_runtime
    from agent_backend.main import create_app
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agent_backend.core.config_loader import get_schema_runtime
    from agent_backend.main import create_app

from fastapi.testclient import TestClient


def main() -> None:
    runtime = get_schema_runtime()
    print("Loaded schema metadata")
    print("- tables:", sorted(runtime.tree.keys()))
    print("- column_count:", len(runtime.by_column_path))
    print("- semantic_keys:", sorted(runtime.by_semantic.keys()))
    print("- synonym_keys:", len(runtime.synonyms))
    print("- example column s_machine.Ip_C:", runtime.by_column_path["s_machine.Ip_C"])

    client = TestClient(create_app())
    health = client.get("/api/v1/health").json()
    summary = client.get("/api/v1/metadata/summary").json()

    print("\nAPI responses")
    print("- /api/v1/health:")
    print(json.dumps(health, ensure_ascii=False))
    print("- /api/v1/metadata/summary:")
    print(json.dumps(summary, ensure_ascii=False))

    sql_gen = client.post(
        "/api/v1/sql/generate",
        json={"question": "查询 192.168.1.10 的告警信息 最近 5 条", "lognum": "admin"},
    ).json()
    print("- /api/v1/sql/generate:")
    print(json.dumps(sql_gen, ensure_ascii=False))


if __name__ == "__main__":
    main()

