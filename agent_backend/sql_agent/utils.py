"""
SQL工具函数模块

文件功能：
    提供SQL文本处理相关的通用工具函数。

在系统架构中的定位：
    位于SQL Agent模块的底层工具层，被 service.py 和 sql_tool.py 调用。

核心函数：
    - clean_sql_markdown: 清理LLM输出中包裹SQL的Markdown格式标记

关联文件：
    - agent_backend/sql_agent/service.py: SQL生成后清理格式
    - agent_backend/agent/tools/sql_tool.py: SQL生成后清理格式
"""
import re


def clean_sql_markdown(sql: str) -> str:
    """
    清理LLM输出中包裹SQL的Markdown格式标记。

    LLM生成的SQL常被 ```sql ... ``` 代码块或反引号包裹，
    此函数移除这些格式标记，提取纯SQL文本。

    处理规则：
        1. 去除首尾空白
        2. 移除开头的 ```sql 或 ``` 标记
        3. 移除结尾的 ``` 标记
        4. 移除SQL中的反引号包裹（如 `table_name` → table_name）

    参数：
        sql: LLM原始输出的SQL文本

    返回：
        清理后的纯SQL文本
    """
    sql = sql.strip()
    sql = re.sub(r"^```sql\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"^```\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    sql = re.sub(r"`([^`]+)`", r"\1", sql)
    return sql.strip()
