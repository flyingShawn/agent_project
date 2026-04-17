from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey
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
