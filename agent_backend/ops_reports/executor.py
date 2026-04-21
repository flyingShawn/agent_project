"""
运维简报生成执行器

文件功能：
    实现运维智能简报的完整生成流程，包括数据采集、趋势分析、异常检测、
    摘要生成（模板+LLM润色）和Markdown报告构建。

在系统架构中的定位：
    位于运维简报模块的核心执行层，被 OpsReportManager 调用。
    直接查询业务数据库（SQL Server/MySQL）获取运维指标数据。

主要使用场景：
    - 定时任务自动生成运维简报
    - API手动触发生成运维简报

核心类：
    - OpsReportExecutor: 运维简报执行器

数据采集指标：
    - 在线状态: 在线客户端数、总数、在线率、未开机设备数
    - 远程协助: 远程次数统计、Top20客户端、部门关联
    - USB使用: U盘日志总数、Top20设备、Top20电脑

报告生成流程：
    1. 采集在线/远程/USB三类指标数据
    2. 加载上一期快照进行趋势对比
    3. 基于阈值检测异常波动
    4. 生成模板摘要（可选LLM润色）
    5. 构建Markdown格式报告
    6. 存储报告和指标快照到SQLite

专有技术说明：
    - 远程协助日志解析使用正则匹配 AdminLog 中的特定格式
    - LLM润色使用低温度(0.2)确保不修改数字和事实
    - 异常检测基于可配置阈值，支持绝对值和百分比两种判定方式
    - 严重级别: normal(无异常) / attention(1项异常) / warning(≥2项异常)

关联文件：
    - agent_backend/ops_reports/manager.py: OpsReportManager 调用执行器
    - agent_backend/core/config.py: get_database_url 业务数据库配置
    - agent_backend/db/chat_history.py: async_session SQLite会话
    - agent_backend/db/models.py: OpsReport, OpsMetricSnapshot ORM模型
    - agent_backend/llm/factory.py: get_llm LLM润色调用
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import create_engine, text

from agent_backend.core.config import get_database_url
from agent_backend.db.chat_history import async_session
from agent_backend.db.models import OpsMetricSnapshot, OpsReport
from agent_backend.llm.factory import get_llm

logger = logging.getLogger(__name__)

REMOTE_DOINFO_PATTERN = re.compile(
    r"^开始远程协助---机器:\[(?P<machine>[^\]]+)\]\[(?P<ip>[^\]]+)\]$"
)


class OpsReportExecutor:
    """
    运维简报生成执行器

    负责从业务数据库采集运维指标、分析趋势、检测异常、生成报告。
    使用SQLAlchemy同步引擎查询业务数据库，通过asyncio.to_thread实现异步调用。
    """
    def __init__(self) -> None:
        """
        初始化执行器，创建业务数据库连接引擎。

        异常：
            RuntimeError: 未配置业务数据库URL时抛出
        """
        database_url = get_database_url()
        if not database_url:
            raise RuntimeError("未配置业务数据库，无法生成运维简报")
        self._engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=3600)

    def close(self) -> None:
        """释放数据库连接引擎资源"""
        self._engine.dispose()

    async def generate_report(self, report_key: str, config: dict[str, Any]) -> dict[str, Any]:
        """
        生成运维简报的完整流程。

        执行流程：
            1. 加载上一期指标快照
            2. 采集在线/远程/USB三类指标
            3. 构建趋势对比和异常检测
            4. 生成模板摘要（可选LLM润色）
            5. 构建Markdown报告
            6. 存储报告和快照

        参数：
            report_key: 简报配置标识
            config: 简报配置字典，包含 top_n、lookback_days、llm_polish_enabled、thresholds

        返回：
            包含 report_id、title、summary、content_md、severity、snapshot 等字段的字典
        """
        top_n = int(config.get("top_n", 20))
        lookback_days = int(config.get("lookback_days", 3))
        llm_polish_enabled = bool(config.get("llm_polish_enabled", True))
        thresholds = config.get("thresholds", {})

        now_dt = datetime.now()
        cutoff_dt = now_dt - timedelta(days=lookback_days)
        generated_at = time.time()

        previous_snapshot = await self._load_previous_snapshot(report_key)
        online_metrics = await self._collect_online_metrics(cutoff_dt)
        remote_metrics = await self._collect_remote_metrics(cutoff_dt, top_n)
        usb_metrics = await self._collect_usb_metrics(cutoff_dt, top_n)

        snapshot = {
            "report_key": report_key,
            "generated_at": generated_at,
            "window_start": cutoff_dt.timestamp(),
            "window_end": now_dt.timestamp(),
            "lookback_days": lookback_days,
            "top_n": top_n,
            "online": online_metrics,
            "remote": remote_metrics,
            "usb": usb_metrics,
        }

        snapshot["trends"] = self._build_trends(snapshot, previous_snapshot)
        snapshot["anomalies"] = self._detect_anomalies(snapshot, previous_snapshot, thresholds)

        summary = self._build_template_summary(snapshot)
        if llm_polish_enabled:
            summary = await self._polish_summary(summary, snapshot)

        severity = self._build_severity(snapshot["anomalies"])
        title = f"运维智能简报 {now_dt.strftime('%Y-%m-%d %H:%M')}"
        content_md = self._build_markdown_report(title, summary, snapshot, severity)

        return await self._store_report(
            report_key=report_key,
            title=title,
            summary=summary,
            content_md=content_md,
            severity=severity,
            generated_at=generated_at,
            window_start=cutoff_dt.timestamp(),
            window_end=now_dt.timestamp(),
            snapshot=snapshot,
        )

    async def _query_rows(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        异步执行SQL查询并返回字典列表。

        参数：
            sql: SQL查询语句
            params: 查询参数字典

        返回：
            查询结果行列表，每行为 {列名: 值} 字典
        """
        return await asyncio.to_thread(self._query_rows_sync, sql, params or {})

    def _query_rows_sync(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """
        同步执行SQL查询（内部方法，通过asyncio.to_thread异步调用）。

        参数：
            sql: SQL查询语句
            params: 查询参数字典

        返回：
            查询结果行列表
        """
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()
            keys = list(result.keys())
        return [{key: row[index] for index, key in enumerate(keys)} for row in rows]

    async def _collect_online_metrics(self, cutoff_dt: datetime) -> dict[str, Any]:
        """
        采集客户端在线状态指标。

        查询数据：
            - 当前在线客户端数（onlineinfo表）
            - 客户端总数（s_machine表）
            - 未开机设备数（最近lookback_days未启动的设备）
            - 缺少开机记录的设备数

        参数：
            cutoff_dt: 统计截止时间，早于此时间未开机的设备视为未开机

        返回：
            包含 online_count、total_count、online_rate、not_booted_count、missing_runtime_count 的字典
        """
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

        online_rows = await self._query_rows(
            """
            SELECT COUNT(*) AS online_count
            FROM onlineinfo
            """
        )
        total_rows = await self._query_rows(
            """
            SELECT COUNT(*) AS total_count
            FROM s_machine
            """
        )
        inactive_rows = await self._query_rows(
            """
            SELECT
                SUM(CASE WHEN latest.systemstarttime IS NULL THEN 1 ELSE 0 END) AS missing_runtime_count,
                SUM(
                    CASE
                        WHEN latest.systemstarttime IS NOT NULL
                         AND latest.systemstarttime < :cutoff
                        THEN 1
                        ELSE 0
                    END
                ) AS not_booted_count
            FROM s_machine m
            LEFT JOIN (
                SELECT MtID, MAX(systemstarttime) AS systemstarttime
                FROM a_machineruntime
                GROUP BY MtID
            ) latest ON latest.MtID = m.ID
            """,
            {"cutoff": cutoff_str},
        )

        online_count = int(online_rows[0]["online_count"] if online_rows else 0)
        total_count = int(total_rows[0]["total_count"] if total_rows else 0)
        inactive = inactive_rows[0] if inactive_rows else {}

        missing_runtime_count = int(inactive.get("missing_runtime_count") or 0)
        not_booted_count = int(inactive.get("not_booted_count") or 0)
        online_rate = round((online_count / total_count) * 100, 1) if total_count else 0.0

        return {
            "online_count": online_count,
            "total_count": total_count,
            "online_rate": online_rate,
            "not_booted_count": not_booted_count,
            "missing_runtime_count": missing_runtime_count,
        }

    async def _collect_remote_metrics(self, cutoff_dt: datetime, top_n: int) -> dict[str, Any]:
        """
        采集远程协助指标。

        查询 AdminLog 表中远程协助日志，解析机器名和IP，
        聚合统计每个客户端的被远程次数，返回Top N。

        参数：
            cutoff_dt: 统计起始时间
            top_n: 返回Top N客户端

        返回：
            包含 remote_total_count、parse_failed_count、top_clients 的字典
        """
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
        rows = await self._query_rows(
            """
            SELECT doinfo, AddDate AS add_date
            FROM AdminLog
            WHERE AddDate >= :cutoff
              AND doinfo LIKE '开始远程协助---机器:[%][%]'
            ORDER BY AddDate DESC
            """,
            {"cutoff": cutoff_str},
        )

        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        parsed_count = 0
        parse_failed_count = 0

        for row in rows:
            doinfo = str(row.get("doinfo") or "").strip()
            matched = REMOTE_DOINFO_PATTERN.match(doinfo)
            if not matched:
                parse_failed_count += 1
                continue

            parsed_count += 1
            machine_name = matched.group("machine").strip()
            ip = matched.group("ip").strip()
            add_date = row.get("add_date")
            key = (machine_name, ip)

            current = aggregated.setdefault(
                key,
                {
                    "machine_name": machine_name,
                    "ip": ip,
                    "department": "",
                    "remote_count": 0,
                    "last_remote_time": add_date,
                },
            )
            current["remote_count"] += 1
            if self._is_newer_datetime(add_date, current.get("last_remote_time")):
                current["last_remote_time"] = add_date

        top_clients = sorted(
            aggregated.values(),
            key=lambda item: (
                int(item.get("remote_count") or 0),
                self._sort_datetime_value(item.get("last_remote_time")),
            ),
            reverse=True,
        )[:top_n]

        await self._enrich_remote_departments(top_clients)

        for item in top_clients:
            item["last_remote_time"] = self._format_datetime(item.get("last_remote_time"))

        return {
            "remote_total_count": parsed_count,
            "parse_failed_count": parse_failed_count,
            "top_clients": top_clients,
        }

    async def _enrich_remote_departments(self, top_clients: list[dict[str, Any]]) -> None:
        """
        为远程协助Top客户端补充部门信息。

        根据IP地址关联 s_machine 和 s_group 表查询部门路径，
        直接修改top_clients列表中的department字段。

        参数：
            top_clients: 远程协助Top客户端列表（原地修改）
        """
        ips = [item["ip"] for item in top_clients if item.get("ip")]
        if not ips:
            return

        bind_names: list[str] = []
        params: dict[str, Any] = {}
        for index, ip in enumerate(dict.fromkeys(ips)):
            key = f"ip_{index}"
            bind_names.append(f":{key}")
            params[key] = ip

        rows = await self._query_rows(
            f"""
            SELECT
                m.Ip_C AS ip,
                m.Name_C AS db_machine_name,
                g.deppath AS department
            FROM s_machine m
            LEFT JOIN s_group g ON m.Groupid = g.id
            WHERE m.Ip_C IN ({", ".join(bind_names)})
            """,
            params,
        )
        by_ip = {str(row.get("ip") or ""): row for row in rows}

        for item in top_clients:
            matched = by_ip.get(item.get("ip", ""))
            if not matched:
                continue
            item["department"] = matched.get("department") or ""
            if not item.get("machine_name"):
                item["machine_name"] = matched.get("db_machine_name") or ""

    async def _collect_usb_metrics(self, cutoff_dt: datetime, top_n: int) -> dict[str, Any]:
        """
        采集U盘使用指标。

        查询 usbdb 表统计U盘使用日志，返回Top N设备和Top N电脑。

        参数：
            cutoff_dt: 统计起始时间
            top_n: 返回Top N

        返回：
            包含 usb_total_count、top_devices、top_machines 的字典
        """
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

        total_rows = await self._query_rows(
            """
            SELECT COUNT(*) AS usb_total_count
            FROM usbdb
            WHERE USBPlugTime >= :cutoff
            """,
            {"cutoff": cutoff_str},
        )
        top_devices = await self._query_rows(
            f"""
            SELECT
                COALESCE(NULLIF(TRIM(DeviceDesc), ''), '未知U盘') AS device_name,
                COALESCE(NULLIF(TRIM(FriendName), ''), '') AS friend_name,
                COUNT(*) AS usage_count
            FROM usbdb
            WHERE USBPlugTime >= :cutoff
            GROUP BY
                COALESCE(NULLIF(TRIM(DeviceDesc), ''), '未知U盘'),
                COALESCE(NULLIF(TRIM(FriendName), ''), '')
            ORDER BY usage_count DESC, device_name ASC
            LIMIT {top_n}
            """,
            {"cutoff": cutoff_str},
        )
        top_machines = await self._query_rows(
            f"""
            SELECT
                COALESCE(m.Name_C, '未知设备') AS machine_name,
                COALESCE(m.Ip_C, '') AS ip,
                COUNT(*) AS usage_count
            FROM usbdb u
            LEFT JOIN s_machine m ON u.MtID = m.ID
            WHERE u.USBPlugTime >= :cutoff
            GROUP BY u.MtID, m.Name_C, m.Ip_C
            ORDER BY usage_count DESC, MAX(u.USBPlugTime) DESC
            LIMIT {top_n}
            """,
            {"cutoff": cutoff_str},
        )

        return {
            "usb_total_count": int(total_rows[0]["usb_total_count"] if total_rows else 0),
            "top_devices": [
                {
                    "device_name": row.get("device_name") or "未知U盘",
                    "friend_name": row.get("friend_name") or "",
                    "usage_count": int(row.get("usage_count") or 0),
                }
                for row in top_devices
            ],
            "top_machines": [
                {
                    "machine_name": row.get("machine_name") or "未知设备",
                    "ip": row.get("ip") or "",
                    "usage_count": int(row.get("usage_count") or 0),
                }
                for row in top_machines
            ],
        }

    async def _load_previous_snapshot(self, report_key: str) -> dict[str, Any] | None:
        """
        加载上一期运维指标快照，用于趋势对比。

        参数：
            report_key: 简报配置标识

        返回：
            上一期快照字典，无历史数据时返回None
        """
        from sqlalchemy import select

        async with async_session() as session:
            result = await session.execute(
                select(OpsMetricSnapshot)
                .where(OpsMetricSnapshot.report_key == report_key)
                .order_by(OpsMetricSnapshot.created_at.desc())
                .limit(1)
            )
            snapshot = result.scalar_one_or_none()

        if not snapshot:
            return None

        try:
            return json.loads(snapshot.snapshot_data)
        except json.JSONDecodeError:
            logger.warning("\n[OpsReport] 历史快照 JSON 解析失败，跳过趋势对比")
            return None

    def _build_trends(
        self,
        current: dict[str, Any],
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        构建当前与上一期指标的趋势对比。

        计算在线数、在线率、未开机数、远程次数、U盘日志数的变化量，
        以及Top1远程客户端和Top1 U盘设备/电脑是否变化。

        参数：
            current: 当期指标快照
            previous: 上期指标快照，None时趋势值均为None

        返回：
            趋势对比字典，包含各类delta和changed字段
        """
        def get_number(snapshot: dict[str, Any] | None, *keys: str) -> int | float | None:
            node: Any = snapshot
            for key in keys:
                if not isinstance(node, dict):
                    return None
                node = node.get(key)
            if isinstance(node, (int, float)):
                return node
            return None

        current_remote_top = self._first_or_none(current["remote"]["top_clients"])
        previous_remote_top = self._first_or_none(
            previous.get("remote", {}).get("top_clients", []) if previous else []
        )
        current_usb_device_top = self._first_or_none(current["usb"]["top_devices"])
        previous_usb_device_top = self._first_or_none(
            previous.get("usb", {}).get("top_devices", []) if previous else []
        )
        current_usb_machine_top = self._first_or_none(current["usb"]["top_machines"])
        previous_usb_machine_top = self._first_or_none(
            previous.get("usb", {}).get("top_machines", []) if previous else []
        )

        return {
            "online_count_delta": self._delta(
                get_number(current, "online", "online_count"),
                get_number(previous, "online", "online_count"),
            ),
            "online_rate_delta": self._delta(
                get_number(current, "online", "online_rate"),
                get_number(previous, "online", "online_rate"),
            ),
            "not_booted_count_delta": self._delta(
                get_number(current, "online", "not_booted_count"),
                get_number(previous, "online", "not_booted_count"),
            ),
            "remote_total_count_delta": self._delta(
                get_number(current, "remote", "remote_total_count"),
                get_number(previous, "remote", "remote_total_count"),
            ),
            "remote_top1_count_delta": self._delta(
                current_remote_top.get("remote_count") if current_remote_top else None,
                previous_remote_top.get("remote_count") if previous_remote_top else None,
            ),
            "usb_total_count_delta": self._delta(
                get_number(current, "usb", "usb_total_count"),
                get_number(previous, "usb", "usb_total_count"),
            ),
            "usb_top_device_changed": self._identity_changed(
                current_usb_device_top,
                previous_usb_device_top,
                ("device_name", "friend_name"),
            ),
            "usb_top_machine_changed": self._identity_changed(
                current_usb_machine_top,
                previous_usb_machine_top,
                ("machine_name", "ip"),
            ),
        }

    def _detect_anomalies(
        self,
        current: dict[str, Any],
        previous: dict[str, Any] | None,
        thresholds: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        基于阈值检测运维指标异常波动。

        检测项：
            - online_drop: 在线客户端下降超过阈值（绝对值+百分比双重判定）
            - not_booted_increase: 未开机设备增加超过阈值
            - remote_spike: Top1被远程次数超过阈值且增幅显著
            - usb_spike: U盘日志总数增长超过阈值（绝对值+百分比双重判定）

        参数：
            current: 当期指标快照（含trends）
            previous: 上期指标快照
            thresholds: 阈值配置字典

        返回：
            异常信息列表，每项包含 code 和 message
        """
        trends = current["trends"]
        anomalies: list[dict[str, Any]] = []

        online_drop_abs = int(thresholds.get("online_drop_abs", 5))
        online_drop_pct = float(thresholds.get("online_drop_pct", 0.05))
        not_booted_increase_abs = int(thresholds.get("not_booted_increase_abs", 5))
        remote_top1_min_count = int(thresholds.get("remote_top1_min_count", 8))
        remote_top1_increase_abs = int(thresholds.get("remote_top1_increase_abs", 3))
        usb_total_growth_pct = float(thresholds.get("usb_total_growth_pct", 0.2))
        usb_total_growth_abs = int(thresholds.get("usb_total_growth_abs", 20))

        online_delta = trends.get("online_count_delta")
        if online_delta is not None and online_delta <= -online_drop_abs:
            previous_online = int(previous.get("online", {}).get("online_count", 0)) if previous else 0
            drop_ratio = (abs(online_delta) / previous_online) if previous_online else 0
            if drop_ratio >= online_drop_pct:
                anomalies.append(
                    {
                        "code": "online_drop",
                        "message": f"在线客户端较上一期下降 {abs(int(online_delta))} 台，需要关注。",
                    }
                )

        not_booted_delta = trends.get("not_booted_count_delta")
        if not_booted_delta is not None and not_booted_delta >= not_booted_increase_abs:
            anomalies.append(
                {
                    "code": "not_booted_increase",
                    "message": f"最近三天未开机设备较上一期增加 {int(not_booted_delta)} 台，需要关注。",
                }
            )

        remote_top = self._first_or_none(current["remote"]["top_clients"])
        remote_top_delta = trends.get("remote_top1_count_delta")
        if remote_top and remote_top_delta is not None:
            remote_count = int(remote_top.get("remote_count") or 0)
            if remote_count >= remote_top1_min_count and remote_top_delta >= remote_top1_increase_abs:
                target = remote_top.get("ip") or remote_top.get("machine_name") or "未知设备"
                anomalies.append(
                    {
                        "code": "remote_spike",
                        "message": (
                            f"被远程次数最高的客户端 {target} 达到 {remote_count} 次，"
                            f"较上一期增加 {int(remote_top_delta)} 次。"
                        ),
                    }
                )

        usb_total_delta = trends.get("usb_total_count_delta")
        previous_usb_total = int(previous.get("usb", {}).get("usb_total_count", 0)) if previous else 0
        if usb_total_delta is not None and usb_total_delta >= usb_total_growth_abs:
            growth_ratio = (usb_total_delta / previous_usb_total) if previous_usb_total else 0
            if growth_ratio >= usb_total_growth_pct:
                anomalies.append(
                    {
                        "code": "usb_spike",
                        "message": f"U 盘日志总数较上一期增加 {int(usb_total_delta)} 条，需要关注。",
                    }
                )

        return anomalies

    def _build_template_summary(self, snapshot: dict[str, Any]) -> str:
        """
        基于模板生成运维简报摘要文本。

        按在线状态→远程协助→U盘使用→关注项的顺序组织摘要内容，
        包含趋势变化描述和异常提示。

        参数：
            snapshot: 完整指标快照（含online、remote、usb、trends、anomalies）

        返回：
            模板生成的摘要文本
        """
        online = snapshot["online"]
        remote = snapshot["remote"]
        usb = snapshot["usb"]
        trends = snapshot["trends"]
        lookback_days = snapshot["lookback_days"]

        lines = [
            (
                f"当前系统中，在线客户端 {online['online_count']} 台，总共 {online['total_count']} 台，"
                f"在线率 {online['online_rate']:.1f}%。"
            ),
            self._describe_delta(trends["online_count_delta"], "台", "在线客户端数量"),
            (
                f"最近 {lookback_days} 天有 {online['not_booted_count']} 台设备未开机。"
                f"{self._describe_delta_inline(trends['not_booted_count_delta'], '台', '未开机设备数量')}"
            ),
        ]

        if online["missing_runtime_count"] > 0:
            lines.append(f"另有 {online['missing_runtime_count']} 台设备缺少开机记录。")

        top_remote = self._first_or_none(remote["top_clients"])
        if top_remote:
            remote_target = top_remote.get("ip") or top_remote.get("machine_name") or "未知设备"
            delta_text = self._describe_delta_inline(trends["remote_top1_count_delta"], "次", "Top1 被远程次数")
            lines.append(
                (
                    f"最近 {lookback_days} 天共统计远程协助 {remote['remote_total_count']} 次。"
                    f"被远程次数最多的客户端是 {remote_target}，达到 {top_remote['remote_count']} 次。{delta_text}"
                )
            )
        else:
            lines.append(f"最近 {lookback_days} 天未统计到可解析的远程协助日志。")

        top_usb_device = self._first_or_none(usb["top_devices"])
        top_usb_machine = self._first_or_none(usb["top_machines"])
        if top_usb_device:
            lines.append(
                (
                    f"最近 {lookback_days} 天共统计 U 盘日志 {usb['usb_total_count']} 条。"
                    f"使用次数最多的 U 盘为 {self._compose_usb_name(top_usb_device)}，"
                    f"出现 {top_usb_device['usage_count']} 次。"
                )
            )
        else:
            lines.append(f"最近 {lookback_days} 天未统计到 U 盘使用日志。")

        if top_usb_machine:
            machine_label = top_usb_machine["machine_name"]
            if top_usb_machine["ip"]:
                machine_label = f"{machine_label} / {top_usb_machine['ip']}"
            lines.append(f"使用 U 盘次数最多的电脑为 {machine_label}，出现 {top_usb_machine['usage_count']} 次。")

        if snapshot["anomalies"]:
            lines.append("重点关注：" + "；".join(item["message"] for item in snapshot["anomalies"]))

        return "\n".join(lines)

    async def _polish_summary(self, summary: str, snapshot: dict[str, Any]) -> str:
        """
        使用LLM润色运维简报摘要。

        LLM被约束为只能润色语气和表达，不允许修改任何数字和事实。
        润色失败时回退到模板摘要。

        参数：
            summary: 模板生成的原始摘要
            snapshot: 指标快照（作为LLM参考上下文）

        返回：
            润色后的摘要文本，失败时返回原始摘要
        """
        try:
            llm = get_llm(streaming=False, temperature=0.2)
            system_prompt = (
                "你是运维简报润色助手。"
                "你只能润色语气和表达，不允许修改、增加、删除任何数字、时间、IP、次数或事实。"
                "保留原有段落结构，输出中文纯文本。"
            )
            human_prompt = (
                "请把下面这份运维简报摘要润色得更自然，但不要改动任何数字和事实。\n\n"
                f"结构化快照：{json.dumps(snapshot, ensure_ascii=False)}\n\n"
                f"原始摘要：\n{summary}"
            )
            response = await asyncio.to_thread(
                llm.invoke,
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_prompt),
                ],
            )
            polished = str(response.content or "").strip()
            return polished or summary
        except Exception as exc:
            logger.warning(f"\n[OpsReport] LLM 润色失败，回退模板摘要: {exc}")
            return summary

    def _build_markdown_report(
        self,
        title: str,
        summary: str,
        snapshot: dict[str, Any],
        severity: str,
    ) -> str:
        """
        构建Markdown格式的运维简报。

        报告结构：标题→概览→在线状态→远程协助Top20→U盘使用统计→关注项

        参数：
            title: 报告标题
            summary: 摘要文本
            snapshot: 指标快照
            severity: 严重级别（normal/attention/warning）

        返回：
            Markdown格式的完整报告文本
        """
        generated_label = datetime.fromtimestamp(snapshot["generated_at"]).strftime("%Y-%m-%d %H:%M:%S")
        window_start = datetime.fromtimestamp(snapshot["window_start"]).strftime("%Y-%m-%d %H:%M:%S")
        window_end = datetime.fromtimestamp(snapshot["window_end"]).strftime("%Y-%m-%d %H:%M:%S")
        online = snapshot["online"]
        remote = snapshot["remote"]
        usb = snapshot["usb"]
        trends = snapshot["trends"]

        sections = [
            f"# {title}",
            "",
            f"- 生成时间：{generated_label}",
            f"- 统计窗口：{window_start} 至 {window_end}",
            f"- 严重级别：{severity}",
            "",
            "## 概览",
            summary,
            "",
            "## 在线状态",
            f"- 当前在线客户端：{online['online_count']} 台",
            f"- 客户端总数：{online['total_count']} 台",
            f"- 在线率：{online['online_rate']:.1f}%",
            f"- 最近 {snapshot['lookback_days']} 天未开机设备：{online['not_booted_count']} 台",
            f"- 缺少开机记录设备：{online['missing_runtime_count']} 台",
            f"- 较上一期在线数变化：{self._format_delta_text(trends['online_count_delta'], '台')}",
            f"- 较上一期在线率变化：{self._format_delta_text(trends['online_rate_delta'], '%', precision=1)}",
            "",
            "## 远程协助 Top20",
        ]

        if remote["top_clients"]:
            sections.append(
                self._build_markdown_table(
                    remote["top_clients"],
                    [
                        ("rank", "排名"),
                        ("ip", "IP"),
                        ("machine_name", "电脑名"),
                        ("department", "部门"),
                        ("remote_count", "被远程次数"),
                        ("last_remote_time", "最近远程时间"),
                    ],
                    with_rank=True,
                )
            )
        else:
            sections.append("最近统计窗口内没有可解析的远程协助记录。")

        top_remote = self._first_or_none(remote["top_clients"])
        if top_remote:
            target = top_remote.get("ip") or top_remote.get("machine_name") or "未知设备"
            sections.extend(
                [
                    "",
                    (
                        f"最近 {snapshot['lookback_days']} 天共统计远程协助 {remote['remote_total_count']} 次，"
                        f"Top1 客户端为 {target}，达到 {top_remote['remote_count']} 次，"
                        f"较上一期变化 {self._format_delta_text(trends['remote_top1_count_delta'], '次')}。"
                    ),
                ]
            )

        sections.extend(
            [
                "",
                "## U 盘使用统计",
                f"- 最近 {snapshot['lookback_days']} 天 U 盘日志总数：{usb['usb_total_count']} 条",
                f"- 较上一期变化：{self._format_delta_text(trends['usb_total_count_delta'], '条')}",
            ]
        )

        top_usb_device = self._first_or_none(usb["top_devices"])
        if top_usb_device:
            sections.append(
                f"- 使用次数最多的 U 盘：{self._compose_usb_name(top_usb_device)}，出现 {top_usb_device['usage_count']} 次"
            )

        top_usb_machine = self._first_or_none(usb["top_machines"])
        if top_usb_machine:
            machine_label = top_usb_machine["machine_name"]
            if top_usb_machine["ip"]:
                machine_label = f"{machine_label} / {top_usb_machine['ip']}"
            sections.append(
                f"- 使用 U 盘次数最多的电脑：{machine_label}，出现 {top_usb_machine['usage_count']} 次"
            )

        sections.extend(["", "### U 盘设备 Top20"])
        if usb["top_devices"]:
            sections.append(
                self._build_markdown_table(
                    usb["top_devices"],
                    [
                        ("rank", "排名"),
                        ("device_name", "U 盘名称"),
                        ("friend_name", "备注"),
                        ("usage_count", "使用次数"),
                    ],
                    with_rank=True,
                )
            )
        else:
            sections.append("最近统计窗口内没有 U 盘设备使用记录。")

        sections.extend(["", "### U 盘电脑 Top20"])
        if usb["top_machines"]:
            sections.append(
                self._build_markdown_table(
                    usb["top_machines"],
                    [
                        ("rank", "排名"),
                        ("machine_name", "电脑名"),
                        ("ip", "IP"),
                        ("usage_count", "使用次数"),
                    ],
                    with_rank=True,
                )
            )
        else:
            sections.append("最近统计窗口内没有 U 盘电脑使用记录。")

        sections.extend(["", "## 关注项"])
        if snapshot["anomalies"]:
            sections.extend(f"- {item['message']}" for item in snapshot["anomalies"])
        else:
            sections.append("- 本期未发现达到阈值的异常波动。")

        return "\n".join(sections).strip()

    async def _store_report(
        self,
        *,
        report_key: str,
        title: str,
        summary: str,
        content_md: str,
        severity: str,
        generated_at: float,
        window_start: float,
        window_end: float,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """
        将报告和指标快照存储到SQLite数据库。

        同时写入 OpsReport（报告内容）和 OpsMetricSnapshot（指标快照）两条记录。

        参数：
            report_key: 简报配置标识
            title: 报告标题
            summary: 摘要文本
            content_md: Markdown格式报告内容
            severity: 严重级别
            generated_at: 生成时间戳
            window_start: 统计窗口起始时间戳
            window_end: 统计窗口结束时间戳
            snapshot: 指标快照字典

        返回：
            包含完整报告信息的字典
        """
        report_id = uuid.uuid4().hex
        now = time.time()

        async with async_session() as session:
            session.add(
                OpsReport(
                    report_id=report_id,
                    report_key=report_key,
                    title=title,
                    summary=summary,
                    content_md=content_md,
                    severity=severity,
                    unread=1,
                    generated_at=generated_at,
                    window_start=window_start,
                    window_end=window_end,
                    created_at=now,
                )
            )
            session.add(
                OpsMetricSnapshot(
                    report_id=report_id,
                    report_key=report_key,
                    snapshot_data=json.dumps(snapshot, ensure_ascii=False),
                    created_at=now,
                )
            )
            await session.commit()

        return {
            "report_id": report_id,
            "report_key": report_key,
            "title": title,
            "summary": summary,
            "content_md": content_md,
            "severity": severity,
            "unread": True,
            "generated_at": generated_at,
            "window_start": window_start,
            "window_end": window_end,
            "snapshot": snapshot,
        }

    @staticmethod
    def _delta(current: int | float | None, previous: int | float | None) -> int | float | None:
        if current is None or previous is None:
            return None
        return current - previous

    @staticmethod
    def _first_or_none(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        return rows[0] if rows else None

    @staticmethod
    def _identity_changed(
        current: dict[str, Any] | None,
        previous: dict[str, Any] | None,
        fields: tuple[str, ...],
    ) -> bool | None:
        if not current or not previous:
            return None
        return tuple(current.get(field) for field in fields) != tuple(
            previous.get(field) for field in fields
        )

    @staticmethod
    def _is_newer_datetime(current: Any, existing: Any) -> bool:
        return OpsReportExecutor._sort_datetime_value(current) > OpsReportExecutor._sort_datetime_value(existing)

    @staticmethod
    def _sort_datetime_value(value: Any) -> tuple[int, str]:
        if value is None:
            return (0, "")
        if isinstance(value, datetime):
            return (1, value.strftime("%Y-%m-%d %H:%M:%S"))
        return (1, str(value))

    @staticmethod
    def _format_datetime(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    @staticmethod
    def _build_severity(anomalies: list[dict[str, Any]]) -> str:
        if len(anomalies) >= 2:
            return "warning"
        if anomalies:
            return "attention"
        return "normal"

    @staticmethod
    def _compose_usb_name(item: dict[str, Any]) -> str:
        device_name = str(item.get("device_name") or "未知U盘").strip()
        friend_name = str(item.get("friend_name") or "").strip()
        return f"{device_name} / {friend_name}" if friend_name else device_name

    @staticmethod
    def _describe_delta(delta: int | float | None, unit: str, label: str) -> str:
        if delta is None:
            return f"{label}暂无上一期对比。"
        if delta == 0:
            return f"{label}较上一期持平。"
        if delta > 0:
            return f"{label}较上一期增加 {OpsReportExecutor._format_delta_number(delta)} {unit}。"
        return f"{label}较上一期下降 {OpsReportExecutor._format_delta_number(abs(delta))} {unit}。"

    @staticmethod
    def _describe_delta_inline(delta: int | float | None, unit: str, label: str) -> str:
        if delta is None:
            return f"{label}暂无上一期对比。"
        if delta == 0:
            return f"{label}较上一期持平。"
        if delta > 0:
            return f"{label}较上一期增加 {OpsReportExecutor._format_delta_number(delta)} {unit}。"
        return f"{label}较上一期下降 {OpsReportExecutor._format_delta_number(abs(delta))} {unit}。"

    @staticmethod
    def _format_delta_number(value: int | float) -> str:
        if isinstance(value, int) or float(value).is_integer():
            return str(int(value))
        return str(round(float(value), 1))

    @staticmethod
    def _format_delta_text(delta: int | float | None, unit: str, precision: int = 0) -> str:
        if delta is None:
            return "暂无上一期对比"
        if delta == 0:
            return "持平"
        number = round(float(abs(delta)), precision) if precision else abs(delta)
        if float(number).is_integer():
            number = int(number)
        direction = "增加" if delta > 0 else "下降"
        return f"{direction} {number}{unit}"

    @staticmethod
    def _build_markdown_table(
        rows: list[dict[str, Any]],
        columns: list[tuple[str, str]],
        *,
        with_rank: bool = False,
    ) -> str:
        if not rows:
            return ""

        header = "| " + " | ".join(label for _, label in columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        lines = [header, separator]

        for index, row in enumerate(rows, start=1):
            payload = dict(row)
            if with_rank:
                payload["rank"] = index
            values = []
            for key, _ in columns:
                value = payload.get(key, "")
                if value is None:
                    value = ""
                values.append(str(value).replace("|", "\\|").replace("\n", " "))
            lines.append("| " + " | ".join(values) + " |")

        return "\n".join(lines)
