"""
ORM 数据模型模块

文件功能：
    定义所有 SQLAlchemy ORM 模型，映射到 SQLite 数据库表。
    包含聊天历史和定时任务两大业务领域的数据模型。

在系统架构中的定位：
    位于数据访问层，被 db/chat_history.py 的 async_session 操作，
    被 scheduler/manager.py、api/v1/ 等业务层通过 SQLAlchemy 查询使用。

主要使用场景：
    - 聊天对话和消息的持久化存储
    - 定时任务定义和执行结果的持久化存储

核心模型：
    - Conversation: 聊天对话记录
    - Message: 对话中的单条消息
    - AgentTask: 定时任务定义
    - AgentTaskResult: 定时任务执行结果

关联文件：
    - agent_backend/db/chat_history.py: Base 基类定义、async_session 会话管理
    - agent_backend/scheduler/manager.py: 操作 AgentTask / AgentTaskResult
    - agent_backend/api/v1/conversations.py: 操作 Conversation / Message
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
        intent: 意图识别结果（如 "sql_query"、"scheduler"）
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


class AgentTask(Base):
    """
    定时任务定义模型。

    映射到 agent_task 表，存储定时任务的完整定义信息。
    由 SchedulerManager 管理，支持 interval（固定间隔）和 cron（cron表达式）两种调度类型。

    字段说明：
        id: 自增主键
        task_id: 任务唯一标识，格式为 {agent_name}_{task_type}_{uuid8}
        agent_name: 所属智能体名称，由环境变量 AGENT_NAME 决定
        task_name: 任务名称，如"统计在线客户端数量"（同名活跃任务不可重复）
        task_type: 调度类型，"interval" 或 "cron"
        task_config: 调度配置JSON，interval 含 interval_seconds，cron 含 cron_expr
        sql_template: 要周期执行的 SQL 模板
        description: 任务自然语言描述
        status: 任务状态，"active" / "paused" / "completed"
        last_run_at: 最后执行时间戳
        next_run_at: 下次预计执行时间戳
        created_by: 创建来源，"system"（配置文件）或 "chat"（对话创建）
        created_at: 创建时间戳
        updated_at: 最后更新时间戳

    索引：
        - idx_agent_task_task_id: task_id 唯一索引
        - idx_agent_task_status: status 普通索引

    状态流转：
        active → paused（暂停）→ active（恢复）
        active/paused → completed（软删除）
    """
    __tablename__ = "agent_task"
    __table_args__ = (
        Index("idx_agent_task_task_id", "task_id", unique=True),
        Index("idx_agent_task_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), nullable=False, unique=True)
    agent_name = Column(String(128), nullable=False)
    task_name = Column(String(256), nullable=False)
    task_type = Column(String(32), nullable=False, default="interval")
    task_config = Column(Text, nullable=False)
    sql_template = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="active")
    last_run_at = Column(Float, nullable=True)
    next_run_at = Column(Float, nullable=True)
    created_by = Column(String(64), nullable=False, default="system")
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)


class AgentTaskResult(Base):
    """
    定时任务执行结果模型。

    映射到 agent_task_result 表，记录每次任务执行的详细结果。
    由 TaskExecutor 写入，SchedulerManager 定期清理过期记录。

    字段说明：
        id: 自增主键
        task_id: 关联的任务ID
        agent_name: 执行任务的智能体名称
        run_at: 执行开始时间戳
        status: 执行状态，"success" 或 "error"
        result_data: 查询结果JSON字符串（超过64KB时截断）
        result_summary: 结果摘要文本（如"查询返回 5 行数据"）
        row_count: 结果行数
        error_message: 错误信息（status=error 时）
        duration_ms: 执行耗时（毫秒）
        created_at: 记录创建时间戳

    索引：
        - idx_agent_task_result_task_id: task_id 普通索引（按任务查询结果）
        - idx_agent_task_result_run_at: run_at 普通索引（按时间范围清理）

    数据生命周期：
        由 SchedulerManager._cleanup_old_results() 每天凌晨3:00自动清理
        超过 RESULT_RETENTION_DAYS（默认7天）的记录。
    """
    __tablename__ = "agent_task_result"
    __table_args__ = (
        Index("idx_agent_task_result_task_id", "task_id"),
        Index("idx_agent_task_result_run_at", "run_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), nullable=False)
    agent_name = Column(String(128), nullable=False)
    run_at = Column(Float, nullable=False)
    status = Column(String(16), nullable=False, default="success")
    result_data = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(Float, nullable=False)
