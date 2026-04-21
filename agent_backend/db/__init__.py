"""
数据库模块公共接口

文件功能：
    导出数据库模块的核心组件，提供SQLite异步引擎和ORM模型。

在系统架构中的定位：
    位于数据持久化层的顶层，被API层和业务模块引用。

核心导出：
    - init_db: 初始化数据库（创建表结构）
    - get_session: 获取同步数据库会话
    - async_session: 获取异步数据库会话工厂
    - Conversation: 会话ORM模型
    - Message: 消息ORM模型

关联文件：
    - agent_backend/db/chat_history.py: SQLite异步引擎和会话管理
    - agent_backend/db/models.py: ORM模型定义
"""
from .chat_history import init_db, get_session, async_session
from .models import Conversation, Message
