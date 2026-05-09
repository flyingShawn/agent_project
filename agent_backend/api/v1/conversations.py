"""
聊天对话管理 REST API 路由模块

文件功能：
    定义聊天对话管理的 REST API 端点，提供对话的创建、查询、
    标题更新和软删除等 HTTP 接口。

在系统架构中的定位：
    位于 API 路由层，是前端与对话数据之间的桥梁。
    - 对上：前端通过 HTTP 请求调用这些接口管理对话
    - 对下：通过 SQLAlchemy AsyncSession 操作 Conversation / Message 模型

主要使用场景：
    - 前端对话列表页加载和分页
    - 新建对话、查看对话详情
    - 修改对话标题、删除对话

核心端点：
    - GET /conversations: 获取用户对话列表（分页）
    - GET /conversations/{id}: 获取对话详情及消息
    - POST /conversations: 创建新对话
    - PUT /conversations/{id}/title: 更新对话标题
    - DELETE /conversations/{id}: 软删除对话

路由前缀：
    /api/v1（由 routes.py 挂载）

关联文件：
    - agent_backend/db/chat_history.py: get_session 异步会话依赖
    - agent_backend/db/models.py: Conversation / Message ORM 模型
    - agent_backend/api/routes.py: 路由注册入口
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from agent_backend.api.external_identity import ExternalIdentity, require_external_identity
from agent_backend.db.chat_history import get_session
from agent_backend.db.models import Conversation, Message
from agent_backend.db.utils import commit_or_rollback, now_utc, to_epoch_seconds

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])


class ConversationCreateRequest(BaseModel):
    user_id: str = Field(default="admin")


class ConversationCreateResponse(BaseModel):
    id: str
    title: str
    created_at: float


class ConversationItem(BaseModel):
    id: str
    title: str
    user_id: str
    created_at: float
    updated_at: float


class ConversationListResponse(BaseModel):
    items: list[ConversationItem]
    total: int


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    intent: str | None = None
    charts: str | None = None
    created_at: float


class ConversationDetailResponse(BaseModel):
    id: str
    title: str
    user_id: str
    created_at: float
    updated_at: float
    messages: list[MessageItem]


class TitleUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=50)


class TitleUpdateResponse(BaseModel):
    success: bool
    title: str


class DeleteResponse(BaseModel):
    success: bool


@router.get("/{agent_type}/conversations", response_model=ConversationListResponse)
async def list_conversations(
    agent_type: str,
    current_user: ExternalIdentity = Depends(require_external_identity),
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_session),
):
    count_stmt = select(func.count()).select_from(Conversation).where(
        Conversation.user_id == current_user.user_id,
        Conversation.is_deleted.is_(False),
        Conversation.agent_type == agent_type,
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Conversation)
        .where(
            Conversation.user_id == current_user.user_id,
            Conversation.is_deleted.is_(False),
            Conversation.agent_type == agent_type,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    return ConversationListResponse(
        items=[
            ConversationItem(
                id=c.id,
                title=c.title,
                user_id=c.user_id,
                created_at=to_epoch_seconds(c.created_at),
                updated_at=to_epoch_seconds(c.updated_at),
            )
            for c in conversations
        ],
        total=total,
    )


@router.get("/{agent_type}/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    agent_type: str,
    conversation_id: str,
    current_user: ExternalIdentity = Depends(require_external_identity),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.user_id,
        Conversation.agent_type == agent_type,
        Conversation.is_deleted.is_(False),
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    msg_result = await db.execute(msg_stmt)
    msgs = msg_result.scalars().all()

    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        user_id=conv.user_id,
        created_at=to_epoch_seconds(conv.created_at),
        updated_at=to_epoch_seconds(conv.updated_at),
        messages=[
            MessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                intent=m.intent,
                charts=m.charts,
                created_at=to_epoch_seconds(m.created_at),
            )
            for m in msgs
        ],
    )


@router.post("/{agent_type}/conversations", response_model=ConversationCreateResponse)
async def create_conversation(
    agent_type: str,
    req: ConversationCreateRequest,
    current_user: ExternalIdentity = Depends(require_external_identity),
    db: AsyncSession = Depends(get_session),
):
    now = now_utc()
    conv = Conversation(
        id=str(uuid.uuid4()),
        title="新对话",
        user_id=current_user.user_id,
        agent_type=agent_type,
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )
    db.add(conv)
    await commit_or_rollback(db)
    await db.refresh(conv)

    logger.info(f"\n[Conv] 创建新会话: {conv.id[:8]}... (用户: {req.user_id})")
    return ConversationCreateResponse(
        id=conv.id,
        title=conv.title,
        created_at=to_epoch_seconds(conv.created_at),
    )


@router.put("/{agent_type}/conversations/{conversation_id}/title", response_model=TitleUpdateResponse)
async def update_conversation_title(
    agent_type: str,
    conversation_id: str,
    req: TitleUpdateRequest,
    current_user: ExternalIdentity = Depends(require_external_identity),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.user_id,
        Conversation.agent_type == agent_type,
        Conversation.is_deleted.is_(False),
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    conv.title = req.title
    conv.updated_at = now_utc()
    await commit_or_rollback(db)

    logger.info(f"\n[Conv] 会话标题更新: {conversation_id[:8]}... -> {req.title}")
    return TitleUpdateResponse(success=True, title=conv.title)


@router.delete("/{agent_type}/conversations/{conversation_id}", response_model=DeleteResponse)
async def delete_conversation(
    agent_type: str,
    conversation_id: str,
    current_user: ExternalIdentity = Depends(require_external_identity),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.user_id,
        Conversation.agent_type == agent_type,
        Conversation.is_deleted.is_(False),
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    conv.is_deleted = True
    conv.updated_at = now_utc()
    await commit_or_rollback(db)

    logger.info(f"\n[Conv] 会话已删除: {conversation_id[:8]}...")
    return DeleteResponse(success=True)
