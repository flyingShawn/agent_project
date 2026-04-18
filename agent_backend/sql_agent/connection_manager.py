"""
业务数据库连接管理模块

文件功能：
    管理业务数据库（MySQL/PostgreSQL等）连接的生命周期，实现连接持久化
    和复用。按会话ID管理连接，支持自动过期清理和健康检查自动重连。

在系统架构中的定位：
    位于 SQL Agent 的基础设施层，被 sql_agent/executor.py 调用。
    - 对上：executor 通过 get_or_create_connection() 获取数据库连接
    - 对下：封装 SQLAlchemy 同步引擎的连接管理

主要使用场景：
    - 用户提问时，executor 获取对应会话的数据库连接执行SQL
    - 定时任务执行时，使用 __scheduler__ 会话ID的连接
    - 对话结束时，通过 close_connection() 释放连接

核心类与函数：
    - ConnectionManager: 单例连接管理器
      - get_or_create_connection(): 获取或创建指定会话的数据库连接
      - close_connection(): 关闭指定会话的连接
      - close_all_connections(): 关闭所有连接
      - mark_connection_invalid(): 标记连接为无效
      - get_connection_manager(): 获取单例实例的工厂函数
    - SessionConnection: 会话连接信息数据类

专有技术说明：
    - 单例模式：通过 __new__ + 双重检查锁实现线程安全单例
    - 连接复用：同一会话ID复用同一连接，避免频繁创建/销毁
    - 自动过期：60分钟未使用的连接自动清理（后台守护线程每60秒检查）
    - 健康检查：复用连接前执行 SELECT 1 验证连接有效性
    - 自动重连：健康检查失败时自动关闭旧连接并创建新连接

性能与安全注意事项：
    - pool_pre_ping=True: SQLAlchemy 内置连接健康检查
    - pool_recycle=3600: 连接最大存活1小时，避免数据库端超时
    - 后台清理线程为 daemon 线程，主进程退出时自动终止

关联文件：
    - agent_backend/sql_agent/executor.py: execute_sql() 调用连接管理器
    - agent_backend/api/v1/chat.py: 对话结束时调用 close_connection()
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SessionConnection:
    """会话连接信息"""
    session_id: str
    connection: Any
    engine: Any
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    is_active: bool = True


class ConnectionManager:
    """
    数据库连接管理器
    
    功能：
    - 按会话ID管理数据库连接
    - 实现连接复用
    - 自动过期清理
    - 连接健康检查和自动重连
    """
    
    _instance: ConnectionManager | None = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'ConnectionManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            with self._lock:
                if not hasattr(self, '_initialized'):
                    self._connections: dict[str, SessionConnection] = {}
                    self._cleanup_thread: threading.Thread | None = None
                    self._stop_event: threading.Event = threading.Event()
                    self._initialized = True
                    self._start_cleanup_thread()
                    logger.info("\n✅ ConnectionManager 初始化完成")
    
    def _start_cleanup_thread(self) -> None:
        """启动清理线程"""
        if self._cleanup_thread is not None:
            return
        
        def cleanup_loop():
            logger.info("\n🧹 连接清理线程已启动")
            while not self._stop_event.is_set():
                try:
                    self._cleanup_expired_connections()
                except Exception as e:
                    logger.error(f"❌ 清理线程异常: {e}")
                time.sleep(60)
            logger.info("\n🧹 连接清理线程已停止")
        
        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _cleanup_expired_connections(self) -> None:
        """清理过期的连接（60分钟未使用）"""
        current_time = time.time()
        expired_sessions = []
        
        with self._lock:
            for session_id, conn_info in self._connections.items():
                if conn_info.is_active and (current_time - conn_info.last_used_at > 3600):
                    expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            self.close_connection(session_id, reason="过期自动清理")
    
    def _is_connection_valid(self, connection: Any) -> bool:
        """
        检查连接是否有效
        
        参数：
            connection: 数据库连接对象
        
        返回：
            bool: 连接是否有效
        """
        try:
            from sqlalchemy import text
            connection.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning(f"\n⚠️ 连接健康检查失败: {e}")
            return False
    
    def generate_session_id(self) -> str:
        """生成唯一会话ID"""
        return str(uuid.uuid4())
    
    def get_or_create_connection(self, session_id: str, database_url: str) -> Any:
        """
        获取或创建数据库连接
        
        参数：
            session_id: 会话ID
            database_url: 数据库连接URL
        
        返回：
            数据库连接对象
        """
        from sqlalchemy import create_engine
        
        with self._lock:
            if session_id in self._connections and self._connections[session_id].is_active:
                conn_info = self._connections[session_id]
                
                if self._is_connection_valid(conn_info.connection):
                    conn_info.last_used_at = time.time()
                    logger.info(f"\n🔄 复用数据库连接，会话: {session_id[:8]}...")
                    return conn_info.connection
                else:
                    logger.warning(f"\n⚠️ 连接已失效，重新创建，会话: {session_id[:8]}...")
                    try:
                        conn_info.connection.close()
                        conn_info.engine.dispose()
                    except Exception as e:
                        logger.warning(f"\n⚠️ 关闭旧连接时出错: {e}")
                    del self._connections[session_id]
            
            logger.info(f"\n🆕 创建新数据库连接，会话: {session_id[:8]}...")
            
            try:
                engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=3600)
                connection = engine.connect()
                
                conn_info = SessionConnection(
                    session_id=session_id,
                    connection=connection,
                    engine=engine,
                    created_at=time.time(),
                    last_used_at=time.time(),
                    is_active=True
                )
                
                self._connections[session_id] = conn_info
                logger.info(f"\n✅ 数据库连接创建成功，会话: {session_id[:8]}...")
                return connection
                
            except Exception as e:
                logger.error(f"❌ 创建数据库连接失败: {e}")
                raise
    
    def mark_connection_invalid(self, session_id: str) -> None:
        """
        标记连接为无效（供外部调用，当检测到连接异常时）
        
        参数：
            session_id: 会话ID
        """
        with self._lock:
            if session_id in self._connections:
                logger.warning(f"\n⚠️ 标记连接为无效，会话: {session_id[:8]}...")
                conn_info = self._connections[session_id]
                conn_info.is_active = False
                try:
                    conn_info.connection.close()
                    conn_info.engine.dispose()
                except Exception as e:
                    logger.warning(f"\n⚠️ 关闭连接时出错: {e}")
                del self._connections[session_id]
    
    def close_connection(self, session_id: str, reason: str = "主动关闭") -> None:
        """
        关闭指定会话的数据库连接
        
        参数：
            session_id: 会话ID
            reason: 关闭原因
        """
        with self._lock:
            if session_id not in self._connections:
                logger.warning(f"\n⚠️ 会话连接不存在: {session_id[:8]}...")
                return
            
            conn_info = self._connections[session_id]
            
            if not conn_info.is_active:
                logger.warning(f"\n⚠️ 连接已关闭: {session_id[:8]}...")
                return
            
            try:
                conn_info.connection.close()
                conn_info.engine.dispose()
                conn_info.is_active = False
                logger.info(f"\n🔌 数据库连接已关闭（{reason}），会话: {session_id[:8]}...")
            except Exception as e:
                logger.error(f"❌ 关闭连接失败: {e}")
            finally:
                del self._connections[session_id]
    
    def close_all_connections(self) -> None:
        """关闭所有连接"""
        session_ids = list(self._connections.keys())
        for session_id in session_ids:
            self.close_connection(session_id, reason="关闭所有连接")
    
    def get_active_connection_count(self) -> int:
        """获取当前活跃连接数"""
        with self._lock:
            return sum(1 for conn in self._connections.values() if conn.is_active)
    
    def get_connection_info(self, session_id: str) -> dict | None:
        """获取连接信息"""
        with self._lock:
            if session_id in self._connections:
                conn_info = self._connections[session_id]
                return {
                    "session_id": conn_info.session_id,
                    "created_at": conn_info.created_at,
                    "last_used_at": conn_info.last_used_at,
                    "is_active": conn_info.is_active,
                    "age_seconds": time.time() - conn_info.created_at,
                    "idle_seconds": time.time() - conn_info.last_used_at
                }
        return None
    
    def shutdown(self) -> None:
        """关闭管理器，清理所有资源"""
        logger.info("\n🔻 ConnectionManager 正在关闭...")
        self._stop_event.set()
        self.close_all_connections()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        logger.info("\n✅ ConnectionManager 已关闭")


def get_connection_manager() -> ConnectionManager:
    """获取连接管理器单例"""
    return ConnectionManager()
