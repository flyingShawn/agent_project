"""
ORM 数据模型模块

文件功能：
    定义所有 SQLAlchemy ORM 模型，映射到 PostgreSQL 数据库表。
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
from sqlalchemy import Boolean, Column, DateTime, String, Integer, Text, ForeignKey, Index
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
    __table_args__ = (
        Index("idx_conversation_user_agent_deleted_updated", "user_id", "agent_type", "is_deleted", "updated_at"),
    )

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="新对话")
    user_id = Column(String, nullable=False, default="admin")
    agent_type = Column(String, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)

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
    __table_args__ = (
        Index("idx_message_conversation_created_id", "conversation_id", "created_at", "id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    intent = Column(String, nullable=True)
    charts = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

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
    unread = Column(Boolean, nullable=False, default=True)
    agent_type = Column(String, nullable=False, default="")
    generated_at = Column(DateTime(timezone=True), nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class OpsMetricSnapshot(Base):
    """
    运维简报结构化快照模型。

    映射到 ops_metric_snapshot 表，保存每份简报对应的结构化指标快照，
    供下一次生成简报时做趋势对比。
    """
    __tablename__ = "ops_metric_snapshot"
    __table_args__ = (
        Index("idx_ops_metric_snapshot_report_key", "report_key"),
        Index("idx_ops_metric_snapshot_agent_report_created", "agent_type", "report_key", "created_at"),
        Index("idx_ops_metric_snapshot_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), ForeignKey("ops_report.report_id"), nullable=False)
    report_key = Column(String(64), nullable=False)
    agent_type = Column(String, nullable=False, default="")
    snapshot_data = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class OnlineSnapshot(Base):
    """
    客户端在线状态定时快照模型。

    映射到 online_snapshot 表，每隔一定时间采集一次客户端在线数量和在线率，
    用于绘制在线趋势图表。
    """
    __tablename__ = "online_snapshot"
    __table_args__ = (
        Index("idx_online_snapshot_agent_created", "agent_type", "created_at"),
        Index("idx_online_snapshot_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_type = Column(String, nullable=False, default="")
    online_count = Column(Integer, nullable=False, default=0)
    total_count = Column(Integer, nullable=False, default=0)
    online_rate = Column(Integer, nullable=False, default=0)
    not_booted_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)


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
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class KnowledgeEntry(Base):
    """
    知识库条目模型。

    映射到 knowledge_entries 表，作为知识库录入和编辑的主存储。
    Markdown 文件仅由这些记录派生生成，用于兼容现有 RAG 同步流程。
    """
    __tablename__ = "knowledge_entries"
    __table_args__ = (
        Index("idx_knowledge_agent_type", "agent_type"),
        Index("idx_knowledge_file", "agent_type", "kb_type", "filename"),
        Index("idx_knowledge_deleted", "is_deleted"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_type = Column(String(64), nullable=False)
    kb_type = Column(String(16), nullable=False)
    filename = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    scenario = Column(Text, nullable=False, default="")
    key_tables = Column(Text, nullable=False, default="")
    sql_code = Column(Text, nullable=False, default="")
    answer = Column(Text, nullable=False, default="")
    created_by = Column(String(128), nullable=False, default="legacy")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_by = Column(String(128), nullable=False, default="legacy")
    updated_at = Column(DateTime(timezone=True), nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
