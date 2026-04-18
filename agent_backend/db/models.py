from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey, Index
from sqlalchemy.orm import relationship

from .chat_history import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="新对话")
    user_id = Column(String, nullable=False, default="admin")
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)
    is_deleted = Column(Integer, nullable=False, default=0)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
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
