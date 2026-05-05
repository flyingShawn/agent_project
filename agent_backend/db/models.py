"""
ORM 数据模型模块

文件功能：
    定义所有 SQLAlchemy ORM 模型，映射到 SQLite 数据库表。
    包含聊天历史、运维简报和任务执行三大业务领域的数据模型。

在系统架构中的定位：
    位于数据访问层，被 db/chat_history.py 的 async_session 操作，
    被 api/v1/ 等业务层通过 SQLAlchemy 查询使用。

主要使用场景：
    - 聊天对话和消息的持久化存储
    - 运维简报和指标快照的持久化存储
    - 任务执行记录的持久化存储

核心模型：
    - Conversation: 聊天对话记录
    - Message: 对话中的单条消息
    - OpsReport: 运维简报
    - OpsMetricSnapshot: 运维简报结构化快照
    - TaskExecution: 任务执行记录

关联文件：
    - agent_backend/db/chat_history.py: Base 基类定义、async_session 会话管理
    - agent_backend/api/v1/conversations.py: 操作 Conversation / Message
    - agent_backend/task_engine/executor.py: 操作 TaskExecution
"""
from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey, Index
from sqlalchemy.orm import relationship

from .chat_history import Base


class Conversation(Base):
    """
    聊天对话记录模型。

    映射到 conversations 表，记录每个对话会话的元信息。
    与 Message 为一对多关系（cascade 删除）。

    字段说明：
        id: 对话唯一标识（UUID）
        title: 对话标题，默认"新对话"
        user_id: 所属用户标识，默认"admin"
        created_at: 创建时间戳
        updated_at: 最后更新时间戳
        is_deleted: 软删除标记，0=正常，1=已删除
    """
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="新对话")
    user_id = Column(String, nullable=False, default="admin")
    agent_type = Column(String, nullable=False, default="")
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)
    is_deleted = Column(Integer, nullable=False, default=0)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """
    对话消息模型。

    映射到 messages 表，记录对话中的每条消息（用户/助手）。
    与 Conversation 为多对一关系。

    字段说明：
        id: 自增主键
        conversation_id: 所属对话ID（外键）
        role: 消息角色，"user" 或 "assistant"
        content: 消息文本内容
        intent: 意图识别结果（如 "sql_query"）
        charts: 图表数据（JSON格式，可选）
        created_at: 消息创建时间戳
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    intent = Column(String, nullable=True)
    charts = Column(Text, nullable=True)
    created_at = Column(Float, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")


class OpsReport(Base):
    """
    运维简报模型。

    映射到 ops_report 表，保存每次生成的运维简报正文和摘要。
    """
    __tablename__ = "ops_report"
    __table_args__ = (
        Index("idx_ops_report_report_key", "report_key"),
        Index("idx_ops_report_generated_at", "generated_at"),
        Index("idx_ops_report_unread", "unread"),
    )

    report_id = Column(String(64), primary_key=True)
    report_key = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False, default="")
    content_md = Column(Text, nullable=False, default="")
    severity = Column(String(16), nullable=False, default="normal")
    unread = Column(Integer, nullable=False, default=1)
    agent_type = Column(String, nullable=False, default="")
    generated_at = Column(Float, nullable=False)
    window_start = Column(Float, nullable=False)
    window_end = Column(Float, nullable=False)
    created_at = Column(Float, nullable=False)


class OpsMetricSnapshot(Base):
    """
    运维简报结构化快照模型。

    映射到 ops_metric_snapshot 表，保存每份简报对应的结构化指标快照，
    供下一次生成简报时做趋势对比。
    """
    __tablename__ = "ops_metric_snapshot"
    __table_args__ = (
        Index("idx_ops_metric_snapshot_report_key", "report_key"),
        Index("idx_ops_metric_snapshot_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), ForeignKey("ops_report.report_id"), nullable=False)
    report_key = Column(String(64), nullable=False)
    snapshot_data = Column(Text, nullable=False)
    created_at = Column(Float, nullable=False)


class TaskExecution(Base):
    """
    任务执行记录模型。

    映射到 task_executions 表，记录每次任务执行的参数、状态和结果。
    """
    __tablename__ = "task_executions"
    __table_args__ = (
        Index("idx_task_exec_agent_type", "agent_type"),
        Index("idx_task_exec_status", "status"),
        Index("idx_task_exec_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(String(64), nullable=False, unique=True)
    agent_type = Column(String(64), nullable=False)
    task_id = Column(String(64), nullable=False)
    user_id = Column(String(64), nullable=False, default="admin")
    params = Column(Text, nullable=False, default="{}")
    status = Column(String(16), nullable=False, default="pending")
    result = Column(Text, nullable=True)
    conversation_id = Column(String(64), nullable=True)
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)
