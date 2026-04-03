from __future__ import annotations

import re
from typing import Any

from agent_backend.core.config_loader import SchemaRuntime
from agent_backend.core.errors import AppError
from agent_backend.sql_agent.sql_safety import extract_tables, normalize_sql


def _find_permission(runtime: SchemaRuntime, name: str | None) -> Any:
    if not runtime.raw.permissions:
        raise AppError(code="permission_not_configured", message="未配置 permissions", http_status=500)
    if name is None:
        return runtime.raw.permissions[0]
    for p in runtime.raw.permissions:
        if p.name == name:
            return p
    raise AppError(code="permission_not_found", message=f"未找到权限模板: {name}", http_status=400)


def _first_keyword_pos(sql: str) -> int:
    m = re.search(r"\b(where|group\s+by|order\s+by|having|limit|union)\b", sql, flags=re.I)
    return m.start() if m else len(sql)


def _insert_before_tail(sql: str, snippet: str) -> str:
    pos = _first_keyword_pos(sql)
    head = sql[:pos].rstrip()
    tail = sql[pos:].lstrip()
    if tail:
        return f"{head}\n{snippet}\n{tail}"
    return f"{head}\n{snippet}"


def _append_where(sql: str, condition: str) -> str:
    pos = _first_keyword_pos(sql)
    head = sql[:pos].rstrip()
    tail = sql[pos:].lstrip()
    if re.search(r"\bwhere\b", head, flags=re.I):
        return f"{head}\n  AND ({condition})\n{tail}".rstrip()
    return f"{head}\nWHERE ({condition})\n{tail}".rstrip()


def _replace_allowed_group_sql(text: str, allowed_group_ids_sql: str) -> str:
    return text.replace("{allowed_group_ids_sql}", allowed_group_ids_sql.strip())


def wrap_with_permission(
    *,
    runtime: SchemaRuntime,
    sql: str,
    lognum: str,
    permission_name: str | None,
    params: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    将生成 SQL 按 schema_metadata.yaml 的权限模板进行“行级权限”包装。

    设计目标：
        - 不改变原 SQL 的业务含义
        - 命中规则时自动补 join/where 片段，并将 {allowed_group_ids_sql} 展开为子查询
    """
    permission = _find_permission(runtime, permission_name)

    sql_norm = normalize_sql(sql)
    tables = extract_tables(sql_norm)
    table_set = set(tables.keys())

    out_sql = sql_norm
    allowed_group_ids_sql = permission.allowed_group_ids_sql

    out_params = dict(params)
    for v in permission.variables:
        if v.name in out_params:
            continue
        if v.name in {"admin_lognum", "lognum"}:
            out_params[v.name] = lognum

    if "{allowed_group_ids_sql}" in out_sql:
        out_sql = _replace_allowed_group_sql(out_sql, allowed_group_ids_sql)
        return out_sql, out_params

    for rule in permission.apply_rules:
        if not rule.when_tables_in_query:
            continue
        if not (set(rule.when_tables_in_query) & table_set):
            continue

        cond = rule.where_append_sql
        cond = _replace_allowed_group_sql(cond, allowed_group_ids_sql)

        if rule.machine_anchor is not None:
            anchor_table = rule.machine_anchor.table
            anchor_alias = tables.get(anchor_table) or "m"

            if anchor_table not in table_set:
                source_table = None
                source_alias = None
                for t in rule.when_tables_in_query:
                    if t in table_set and t != anchor_table:
                        source_table = t
                        source_alias = tables.get(t) or t
                        break
                if source_table is None or source_alias is None:
                    raise AppError(
                        code="permission_wrap_failed",
                        message="无法确定权限 join 的来源表别名",
                        http_status=500,
                        details={"tables_in_query": sorted(table_set)},
                    )

                join_sql = rule.machine_anchor.join_from_mtid_sql
                if not join_sql:
                    raise AppError(
                        code="permission_wrap_failed",
                        message="权限规则缺少 join_from_mtid_sql",
                        http_status=500,
                    )
                join_sql = join_sql.format(source_alias=source_alias)
                out_sql = _insert_before_tail(out_sql, join_sql)
                tables[anchor_table] = "m"
                table_set.add(anchor_table)
                anchor_alias = "m"

            if anchor_alias != "m":
                cond = re.sub(r"\bm\.", f"{anchor_alias}.", cond)
        else:
            for t in rule.when_tables_in_query:
                alias = tables.get(t)
                if alias and alias != t:
                    cond = re.sub(r"\b{}\.".format(re.escape(t)), f"{alias}.", cond)

        out_sql = _append_where(out_sql, cond)

    out_sql = _replace_allowed_group_sql(out_sql, allowed_group_ids_sql)
    return out_sql, out_params
