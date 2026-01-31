"""
会话缓存键生成器
为会话相关的缓存操作提供统一的键命名规范
"""

from typing import Optional


class SessionCacheKeys:
    """会话缓存键生成器"""
    
    @staticmethod
    def session_key(session_id: str) -> str:
        """
        生成会话缓存键
        
        Args:
            session_id: 会话ID
            
        Returns:
            缓存键
        """
        return f"session:{session_id}"
    
    @staticmethod
    def session_state_key(session_id: str) -> str:
        """
        生成会话状态缓存键
        
        Args:
            session_id: 会话ID
            
        Returns:
            缓存键
        """
        return f"session_state:{session_id}"
    
    @staticmethod
    def snapshot_key(snapshot_id: str) -> str:
        """
        生成快照缓存键
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            缓存键
        """
        return f"snapshot:{snapshot_id}"
    
    @staticmethod
    def session_snapshots_key(session_id: str) -> str:
        """
        生成会话快照列表缓存键
        
        Args:
            session_id: 会话ID
            
        Returns:
            缓存键
        """
        return f"session_snapshots:{session_id}"
    
    @staticmethod
    def rollback_logs_key(session_id: str) -> str:
        """
        生成回滚日志缓存键
        
        Args:
            session_id: 会话ID
            
        Returns:
            缓存键
        """
        return f"rollback_logs:{session_id}"
    
    @staticmethod
    def session_lock_key(session_id: str) -> str:
        """
        生成会话锁缓存键
        
        Args:
            session_id: 会话ID
            
        Returns:
            缓存键
        """
        return f"session_lock:{session_id}"