"""
运维简报管理器

文件功能：
    管理运维简报的调度、配置加载、报告查询和生命周期。
    使用APScheduler实现定时自动生成，支持手动触发生成。

在系统架构中的定位：
    位于运维简报模块的管理层，被 main.py 启动/关闭，被 api/v1/ops.py 查询。
    通过 OpsReportExecutor 委托实际的报告生成工作。

主要使用场景：
    - 应用启动时自动启动调度器
    - API查询简报列表、详情、最新一期
    - API手动触发生成简报
    - API标记简报已读

核心类：
    - OpsReportManager: 运维简报管理器（单例模式）

管理能力：
    - 定时调度: 基于YAML配置注册定时任务
    - 配置加载: 从 ops_reports.yaml 加载简报配置
    - 报告查询: 列表、详情、最新一期、未读统计
    - 手动触发: 立即生成一期简报
    - 已读标记: 标记简报为已读

关联文件：
    - agent_backend/ops_reports/executor.py: OpsReportExecutor 报告生成器
    - agent_backend/db/chat_history.py: async_session PostgreSQL会话
    - agent_backend/db/models.py: OpsReport, OpsMetricSnapshot ORM模型
    - agent_backend/configs/ops_reports.yaml: 简报配置文件
    - agent_backend/api/v1/ops.py: REST API 调用入口
    - agent_backend/main.py: 应用启动/关闭时调用 start/shutdown
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from agent_backend.db.chat_history import async_session
from agent_backend.db.models import OpsMetricSnapshot, OpsReport, OnlineSnapshot
from agent_backend.db.utils import commit_or_rollback, now_utc, to_epoch_seconds
from agent_backend.ops_reports.executor import OpsReportExecutor

logger = logging.getLogger(__name__)

_CONFIGS_DIR = Path(__file__).parent.parent / "configs"


class OpsReportManager:
    """
    运维简报管理器（单例模式）

    负责调度器的启停、配置加载、报告查询和手动触发。
    通过 APScheduler 实现定时自动生成运维简报。
    """
    _instance: "OpsReportManager | None" = None

    def __new__(cls) -> "OpsReportManager":
        """单例模式：确保全局只有一个管理器实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._scheduler: AsyncIOScheduler | None = None
        self._executor: OpsReportExecutor | None = None
        self._configs: dict[str, dict[str, Any]] = {}
        self._config_paths: dict[str, Path] = {}
        self._run_locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        """
        启动运维简报调度器。

        加载YAML配置，为每个启用的简报任务注册定时调度。
        使用 IntervalTrigger 按配置的间隔时间定时执行。
        """
        if self._scheduler is not None and self._scheduler.running:
            logger.info("\n[OpsReport] 运维简报调度器已在运行")
            return

        self._configs = self._load_configs()
        self._executor = OpsReportExecutor()
        self._scheduler = AsyncIOScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}
        )

        for report_key, config in self._configs.items():
            self._sync_scheduler_job(report_key, config)

        self._scheduler.add_job(
            self._collect_online_snapshot_job,
            IntervalTrigger(minutes=30),
            id="ops_online_snapshot",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info("\n[OpsReport] 运维简报调度器已启动")

    async def shutdown(self) -> None:
        """关闭调度器并释放执行器资源"""
        if self._scheduler is not None:
            logger.info("\n[OpsReport] 正在关闭运维简报调度器...")
            self._scheduler.shutdown(wait=True)
            self._scheduler = None

        if self._executor is not None:
            self._executor.close()
            self._executor = None

        logger.info("\n[OpsReport] 运维简报调度器已关闭")

    def get_info(self) -> dict[str, Any]:
        """
        获取调度器运行状态信息。

        返回：
            包含 running、active_reports、report_keys、jobs 的字典
        """
        configs = list(self._configs.keys()) if self._configs else list(self._load_configs().keys())
        if not self._scheduler:
            return {"running": False, "active_reports": 0, "report_keys": configs, "jobs": []}

        jobs = self._scheduler.get_jobs()
        return {
            "running": self._scheduler.running,
            "active_reports": len(jobs),
            "report_keys": configs,
            "jobs": [
                {"job_id": job.id, "next_run_time": str(job.next_run_time)}
                for job in jobs
            ],
        }

    def get_default_report_key(self, agent_type: str | None = None) -> str:
        """
        获取默认的简报配置标识（第一个启用的配置）。

        异常：
            RuntimeError: 没有可用的简报配置时抛出
        """
        if not self._configs:
            self._configs = self._load_configs()

        for report_key, config in self._configs.items():
            if agent_type and config.get("agent_type") != agent_type:
                continue
            if config.get("enabled", True):
                return report_key
        raise RuntimeError("没有可用的运维简报配置")

    async def run_report_now(self, report_key: str | None = None, agent_type: str | None = None) -> dict[str, Any]:
        if not self._configs:
            self._configs = self._load_configs()
        if self._executor is None:
            self._executor = OpsReportExecutor()

        target_key = report_key or self.get_default_report_key(agent_type)
        config = self._configs.get(target_key)
        if not config:
            raise ValueError(f"运维简报配置不存在: {target_key}")
        if agent_type and config.get("agent_type") != agent_type:
            raise ValueError(f"运维简报配置不属于当前智能体: {target_key}")

        lock_key = f"{config.get('agent_type', '')}::{target_key}"
        lock = self._run_locks.setdefault(lock_key, asyncio.Lock())

        async with lock:
            return await self._executor.generate_report(target_key, config)

    async def list_reports(self, limit: int = 20, unread_only: bool = False, agent_type: str | None = None) -> dict[str, Any]:
        from sqlalchemy import func, select

        async with async_session() as session:
            base_stmt = select(OpsReport)
            count_stmt = select(func.count()).select_from(OpsReport)

            if agent_type:
                base_stmt = base_stmt.where(OpsReport.agent_type == agent_type)
                count_stmt = count_stmt.where(OpsReport.agent_type == agent_type)

            if unread_only:
                base_stmt = base_stmt.where(OpsReport.unread.is_(True))
                count_stmt = count_stmt.where(OpsReport.unread.is_(True))

            reports = (
                await session.execute(
                    base_stmt.order_by(OpsReport.generated_at.desc()).limit(limit)
                )
            ).scalars().all()

            total = (await session.execute(count_stmt)).scalar() or 0
            unread_stmt = select(func.count()).select_from(OpsReport).where(OpsReport.unread.is_(True))
            if agent_type:
                unread_stmt = unread_stmt.where(OpsReport.agent_type == agent_type)
            unread_total = (
                await session.execute(unread_stmt)
            ).scalar() or 0

        return {
            "reports": [self._serialize_report(report, include_content=False) for report in reports],
            "total": total,
            "unread_total": unread_total,
        }

    async def get_latest_report(self, agent_type: str | None = None) -> dict[str, Any]:
        from sqlalchemy import func, select

        async with async_session() as session:
            stmt = select(OpsReport)
            if agent_type:
                stmt = stmt.where(OpsReport.agent_type == agent_type)
            report = (
                await session.execute(
                    stmt.order_by(OpsReport.generated_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            unread_stmt = select(func.count()).select_from(OpsReport).where(OpsReport.unread.is_(True))
            if agent_type:
                unread_stmt = unread_stmt.where(OpsReport.agent_type == agent_type)
            unread_total = (
                await session.execute(unread_stmt)
            ).scalar() or 0

        return {
            "report": self._serialize_report(report, include_content=False) if report else None,
            "unread_total": unread_total,
        }

    async def get_report(self, report_id: str, agent_type: str | None = None) -> dict[str, Any] | None:
        """
        获取指定ID的运维简报详情（含完整内容和指标快照）。

        参数：
            report_id: 简报ID

        返回：
            简报详情字典，不存在时返回None
        """
        from sqlalchemy import select

        async with async_session() as session:
            stmt = select(OpsReport).where(OpsReport.report_id == report_id)
            if agent_type:
                stmt = stmt.where(OpsReport.agent_type == agent_type)
            report = (await session.execute(stmt)).scalar_one_or_none()
            if not report:
                return None

            snapshot = (
                await session.execute(
                    select(OpsMetricSnapshot)
                    .where(
                        OpsMetricSnapshot.report_id == report_id,
                        OpsMetricSnapshot.agent_type == report.agent_type,
                    )
                    .order_by(OpsMetricSnapshot.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        snapshot_data = None
        if snapshot:
            try:
                snapshot_data = json.loads(snapshot.snapshot_data)
            except json.JSONDecodeError:
                logger.warning(f"\n[OpsReport] 快照 JSON 解析失败: report_id={report_id}")

        return self._serialize_report(report, include_content=True, snapshot=snapshot_data)

    async def mark_report_read(self, report_id: str, agent_type: str | None = None) -> dict[str, Any] | None:
        """
        标记指定简报为已读。

        参数：
            report_id: 简报ID

        返回：
            包含 report_id、unread、unread_total 的字典，不存在时返回None
        """
        from sqlalchemy import func, select

        async with async_session() as session:
            stmt = select(OpsReport).where(OpsReport.report_id == report_id)
            if agent_type:
                stmt = stmt.where(OpsReport.agent_type == agent_type)
            report = (await session.execute(stmt)).scalar_one_or_none()
            if not report:
                return None

            report.unread = False
            await commit_or_rollback(session)

            unread_stmt = select(func.count()).select_from(OpsReport).where(OpsReport.unread.is_(True))
            if agent_type:
                unread_stmt = unread_stmt.where(OpsReport.agent_type == agent_type)
            unread_total = (await session.execute(unread_stmt)).scalar() or 0

        return {"report_id": report_id, "unread": False, "unread_total": unread_total}

    async def _run_report_job(self, report_key: str) -> None:
        try:
            await self.run_report_now(report_key)
            logger.info(f"\n[OpsReport] 定时生成简报完成: {report_key}")
        except Exception as exc:
            logger.error(f"\n[OpsReport] 定时生成简报失败: {report_key}, error={exc}")

    def _load_configs(self) -> dict[str, dict[str, Any]]:
        """
        从YAML配置文件加载简报配置。

        通过 AgentRegistry 获取启用了 reports 的智能体配置。

        异常：
            RuntimeError: 配置为空时抛出
        """
        configs: dict[str, dict[str, Any]] = {}
        self._config_paths = {}

        try:
            from agent_backend.agent.registry import get_registry
            registry = get_registry()
            for agent_cfg in registry.get_enabled_agents():
                if not agent_cfg.reports.enabled:
                    continue
                config_path = _CONFIGS_DIR / agent_cfg.config_dir / "ops_reports.yaml"
                if not config_path.exists():
                    logger.warning(f"\n[OpsReport] 运维简报配置不存在: {config_path}")
                    continue
                with open(config_path, "r", encoding="utf-8") as file:
                    data = yaml.safe_load(file) or {}
                for item in data.get("reports", []):
                    report_key = item.get("report_key")
                    if report_key:
                        item["agent_type"] = agent_cfg.agent_type
                        configs[report_key] = item
                        self._config_paths[report_key] = config_path
        except Exception as e:
            logger.warning(f"\n[OpsReport] 加载配置失败: {e}")

        if not configs:
            raise RuntimeError("运维简报配置为空")

        logger.info(f"\n[OpsReport] 已加载 {len(configs)} 个简报配置")
        return configs

    def _build_trigger(self, config: dict[str, Any]):
        schedule = config.get("schedule") or {}
        schedule_type = schedule.get("type")
        if schedule_type in {"daily", "weekly"}:
            hour, minute = self._parse_time(schedule.get("time", "08:00"))
            if schedule_type == "weekly":
                try:
                    weekday = int(schedule.get("weekday") or 1)
                except (TypeError, ValueError):
                    weekday = 1
                day_of_week = (weekday - 1) % 7
                return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
            return CronTrigger(hour=hour, minute=minute)

        interval_seconds = int(config.get("interval_seconds", 7200))
        return IntervalTrigger(seconds=interval_seconds)

    def _sync_scheduler_job(self, report_key: str, config: dict[str, Any]) -> None:
        if self._scheduler is None:
            return
        job_id = f"ops_report::{report_key}"
        if not config.get("enabled", True):
            if self._scheduler.running and self._scheduler.get_job(job_id):
                self._scheduler.remove_job(job_id)
            return
        trigger = self._build_trigger(config)
        self._scheduler.add_job(
            self._run_report_job,
            trigger=trigger,
            id=job_id,
            args=[report_key],
            replace_existing=True,
        )
        logger.info(f"\n[OpsReport] 已注册简报任务: {report_key}, trigger={trigger}")

    @staticmethod
    def _parse_time(value: str) -> tuple[int, int]:
        try:
            hour_text, minute_text = str(value).split(":", 1)
            hour = min(max(int(hour_text), 0), 23)
            minute = min(max(int(minute_text), 0), 59)
            return hour, minute
        except Exception:
            return 8, 0

    def list_definitions(self, agent_type: str | None = None) -> dict[str, Any]:
        """
        获取简报定义列表。

        参数：
            agent_type: 智能体类型筛选

        返回：
            包含 definitions 列表的字典
        """
        if not self._configs:
            self._configs = self._load_configs()

        definitions = []
        for report_key, config in self._configs.items():
            if agent_type and config.get("agent_type") != agent_type:
                continue
            definitions.append({
                "report_key": report_key,
                "name": config.get("name", report_key),
                "enabled": config.get("enabled", True),
                "schedule": config.get("schedule", {}),
                "modules": config.get("modules", []),
                "agent_type": config.get("agent_type", ""),
            })

        return {"definitions": definitions}

    def update_definition(self, report_key: str, body: dict[str, Any], agent_type: str | None = None) -> dict[str, Any]:
        """
        更新简报定义配置，并持久化到 YAML。

        参数：
            report_key: 简报配置标识
            body: 更新内容，支持 enabled、schedule、modules 字段
            agent_type: 智能体类型

        返回：
            更新后的定义字典

        异常：
            ValueError: 配置不存在时抛出
        """
        if not self._configs:
            self._configs = self._load_configs()

        config = self._configs.get(report_key)
        if not config:
            raise ValueError(f"运维简报配置不存在: {report_key}")
        if agent_type and config.get("agent_type") != agent_type:
            raise ValueError(f"运维简报配置不属于当前智能体: {report_key}")

        if "enabled" in body:
            config["enabled"] = body["enabled"]
        if "schedule" in body:
            config["schedule"] = body["schedule"]
        if "modules" in body:
            config["modules"] = body["modules"]
        self._persist_definition(report_key, config)
        self._sync_scheduler_job(report_key, config)

        logger.info(f"\n[OpsReport] 已更新简报定义: {report_key}")

        return {
            "report_key": report_key,
            "name": config.get("name", report_key),
            "enabled": config.get("enabled", True),
            "schedule": config.get("schedule", {}),
            "modules": config.get("modules", []),
            "agent_type": config.get("agent_type", ""),
        }

    def _persist_definition(self, report_key: str, config: dict[str, Any]) -> None:
        config_path = self._config_paths.get(report_key)
        if not config_path:
            raise ValueError(f"运维简报配置文件不存在: {report_key}")

        with open(config_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

        updated = False
        for item in data.get("reports", []):
            if item.get("report_key") != report_key:
                continue
            item["enabled"] = bool(config.get("enabled", True))
            item["schedule"] = copy.deepcopy(config.get("schedule", {}))
            item["modules"] = copy.deepcopy(config.get("modules", []))
            updated = True
            break

        if not updated:
            raise ValueError(f"运维简报配置不存在: {report_key}")

        with open(config_path, "w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)

    @staticmethod
    def _serialize_report(
        report: OpsReport | None,
        *,
        include_content: bool,
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        将ORM模型序列化为API响应字典。

        参数：
            report: OpsReport ORM实例
            include_content: 是否包含完整Markdown内容和快照
            snapshot: 指标快照字典

        返回：
            序列化后的字典，report为None时返回None
        """
        if report is None:
            return None

        payload = {
            "report_id": report.report_id,
            "report_key": report.report_key,
            "title": report.title,
            "summary": report.summary,
            "severity": report.severity,
            "unread": bool(report.unread),
            "agent_type": report.agent_type,
            "generated_at": to_epoch_seconds(report.generated_at),
            "window_start": to_epoch_seconds(report.window_start),
            "window_end": to_epoch_seconds(report.window_end),
        }
        if include_content:
            payload["content_md"] = report.content_md
            payload["snapshot"] = snapshot
        return payload


    async def _collect_online_snapshot_job(self) -> None:
        try:
            if self._executor is None:
                self._executor = OpsReportExecutor()
            from datetime import datetime, timedelta
            now_dt = datetime.now()
            cutoff_dt = now_dt - timedelta(days=3)
            online = await self._executor._collect_online_metrics(cutoff_dt)
            agent_types = set()
            for config in self._configs.values():
                at = config.get("agent_type", "")
                if at:
                    agent_types.add(at)
            if not agent_types:
                agent_types = {""}
            now = now_utc()
            async with async_session() as session:
                for agent_type in agent_types:
                    snapshot = OnlineSnapshot(
                        agent_type=agent_type,
                        online_count=online.get("online_count", 0),
                        total_count=online.get("total_count", 0),
                        online_rate=round(online.get("online_rate", 0) * 10),
                        not_booted_count=online.get("not_booted_count", 0),
                        created_at=now,
                    )
                    session.add(snapshot)
                await commit_or_rollback(session)
            logger.info(f"\n[OpsReport] 在线状态快照采集完成: online={online.get('online_count', 0)}/{online.get('total_count', 0)}")
        except Exception as exc:
            logger.error(f"\n[OpsReport] 在线状态快照采集失败: {exc}")

    async def get_online_trend(self, hours: int = 24, agent_type: str | None = None) -> dict[str, Any]:
        from sqlalchemy import select

        from datetime import timedelta
        cutoff = now_utc() - timedelta(hours=hours)
        async with async_session() as session:
            stmt = select(OnlineSnapshot).order_by(OnlineSnapshot.created_at.asc())
            if agent_type:
                stmt = stmt.where(OnlineSnapshot.agent_type == agent_type)
            stmt = stmt.where(OnlineSnapshot.created_at >= cutoff)
            rows = (await session.execute(stmt)).scalars().all()

        data_points = []
        for row in rows:
            data_points.append({
                "timestamp": to_epoch_seconds(row.created_at),
                "online_count": row.online_count,
                "total_count": row.total_count,
                "online_rate": row.online_rate / 10.0 if row.online_rate else 0.0,
                "not_booted_count": row.not_booted_count,
            })
        return {"data_points": data_points, "hours": hours}


def get_ops_report_manager() -> OpsReportManager:
    """获取运维简报管理器单例实例"""
    return OpsReportManager()
