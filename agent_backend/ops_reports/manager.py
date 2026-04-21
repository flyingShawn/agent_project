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
    - agent_backend/db/chat_history.py: async_session SQLite会话
    - agent_backend/db/models.py: OpsReport, OpsMetricSnapshot ORM模型
    - agent_backend/configs/ops_reports.yaml: 简报配置文件
    - agent_backend/api/v1/ops.py: REST API 调用入口
    - agent_backend/main.py: 应用启动/关闭时调用 start/shutdown
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from agent_backend.db.chat_history import async_session
from agent_backend.db.models import OpsMetricSnapshot, OpsReport
from agent_backend.ops_reports.executor import OpsReportExecutor

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "configs" / "ops_reports.yaml"


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
            if not config.get("enabled", True):
                continue
            interval_seconds = int(config.get("interval_seconds", 7200))
            self._scheduler.add_job(
                self._run_report_job,
                trigger=IntervalTrigger(seconds=interval_seconds),
                id=f"ops_report::{report_key}",
                args=[report_key],
                replace_existing=True,
            )
            logger.info(
                f"\n[OpsReport] 已注册简报任务: {report_key}, interval={interval_seconds}s"
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

    def get_default_report_key(self) -> str:
        """
        获取默认的简报配置标识（第一个启用的配置）。

        异常：
            RuntimeError: 没有可用的简报配置时抛出
        """
        if not self._configs:
            self._configs = self._load_configs()

        for report_key, config in self._configs.items():
            if config.get("enabled", True):
                return report_key
        raise RuntimeError("没有可用的运维简报配置")

    async def run_report_now(self, report_key: str | None = None) -> dict[str, Any]:
        """
        手动触发生成运维简报。

        参数：
            report_key: 简报配置标识，None时使用默认配置

        返回：
            生成结果字典

        异常：
            ValueError: 配置不存在时抛出
        """
        if not self._configs:
            self._configs = self._load_configs()
        if self._executor is None:
            self._executor = OpsReportExecutor()

        target_key = report_key or self.get_default_report_key()
        config = self._configs.get(target_key)
        if not config:
            raise ValueError(f"运维简报配置不存在: {target_key}")

        return await self._executor.generate_report(target_key, config)

    async def list_reports(self, limit: int = 20, unread_only: bool = False) -> dict[str, Any]:
        """
        查询运维简报列表。

        参数：
            limit: 返回数量上限，默认20
            unread_only: 是否只返回未读简报

        返回：
            包含 reports、total、unread_total 的字典
        """
        from sqlalchemy import func, select

        async with async_session() as session:
            base_stmt = select(OpsReport)
            count_stmt = select(func.count()).select_from(OpsReport)

            if unread_only:
                base_stmt = base_stmt.where(OpsReport.unread == 1)
                count_stmt = count_stmt.where(OpsReport.unread == 1)

            reports = (
                await session.execute(
                    base_stmt.order_by(OpsReport.generated_at.desc()).limit(limit)
                )
            ).scalars().all()

            total = (await session.execute(count_stmt)).scalar() or 0
            unread_total = (
                await session.execute(
                    select(func.count()).select_from(OpsReport).where(OpsReport.unread == 1)
                )
            ).scalar() or 0

        return {
            "reports": [self._serialize_report(report, include_content=False) for report in reports],
            "total": total,
            "unread_total": unread_total,
        }

    async def get_latest_report(self) -> dict[str, Any]:
        """
        获取最新一期运维简报。

        返回：
            包含 report、unread_total 的字典
        """
        from sqlalchemy import func, select

        async with async_session() as session:
            report = (
                await session.execute(
                    select(OpsReport).order_by(OpsReport.generated_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            unread_total = (
                await session.execute(
                    select(func.count()).select_from(OpsReport).where(OpsReport.unread == 1)
                )
            ).scalar() or 0

        return {
            "report": self._serialize_report(report, include_content=False) if report else None,
            "unread_total": unread_total,
        }

    async def get_report(self, report_id: str) -> dict[str, Any] | None:
        """
        获取指定ID的运维简报详情（含完整内容和指标快照）。

        参数：
            report_id: 简报ID

        返回：
            简报详情字典，不存在时返回None
        """
        from sqlalchemy import select

        async with async_session() as session:
            report = (
                await session.execute(
                    select(OpsReport).where(OpsReport.report_id == report_id)
                )
            ).scalar_one_or_none()
            if not report:
                return None

            snapshot = (
                await session.execute(
                    select(OpsMetricSnapshot)
                    .where(OpsMetricSnapshot.report_id == report_id)
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

    async def mark_report_read(self, report_id: str) -> dict[str, Any] | None:
        """
        标记指定简报为已读。

        参数：
            report_id: 简报ID

        返回：
            包含 report_id、unread、unread_total 的字典，不存在时返回None
        """
        from sqlalchemy import func, select

        async with async_session() as session:
            report = (
                await session.execute(
                    select(OpsReport).where(OpsReport.report_id == report_id)
                )
            ).scalar_one_or_none()
            if not report:
                return None

            report.unread = 0
            await session.commit()

            unread_total = (
                await session.execute(
                    select(func.count()).select_from(OpsReport).where(OpsReport.unread == 1)
                )
            ).scalar() or 0

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

        异常：
            RuntimeError: 配置文件不存在或配置为空时抛出
        """
        if not _CONFIG_PATH.exists():
            raise RuntimeError(f"运维简报配置不存在: {_CONFIG_PATH}")

        with open(_CONFIG_PATH, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

        configs: dict[str, dict[str, Any]] = {}
        for item in data.get("reports", []):
            report_key = item.get("report_key")
            if report_key:
                configs[report_key] = item

        if not configs:
            raise RuntimeError("运维简报配置为空")

        logger.info(f"\n[OpsReport] 已加载 {len(configs)} 个简报配置")
        return configs

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
            "generated_at": report.generated_at,
            "window_start": report.window_start,
            "window_end": report.window_end,
        }
        if include_content:
            payload["content_md"] = report.content_md
            payload["snapshot"] = snapshot
        return payload


def get_ops_report_manager() -> OpsReportManager:
    """获取运维简报管理器单例实例"""
    return OpsReportManager()
