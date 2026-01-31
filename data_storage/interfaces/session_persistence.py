"""
会话持久化相关接口定义
定义会话、快照、回滚的仓库接口
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from ...models.session_persistence_models import (
    SessionState,
    SessionSnapshot,
    RollbackLog
)


class ISessionRepository(ABC):
    """会话仓库接口"""
    
    @abstractmethod
    async def save(self, session_state: SessionState) -> bool:
        """
        保存会话状态
        
        Args:
            session_state: 会话状态
            
        Returns:
            是否保存成功
        """
        pass
    
    @abstractmethod
    async def get(self, session_id: str) -> Optional[SessionState]:
        """
        获取会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话状态，如果不存在则返回None
        """
        pass
    
    @abstractmethod
    async def update(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新会话状态（部分更新）
        
        Args:
            session_id: 会话ID
            updates: 要更新的字段字典
            
        Returns:
            是否更新成功
        """
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """
        删除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    async def list(
        self,
        filters: Dict[str, Any],
        limit: int = 50,
        offset: int = 0
    ) -> List[SessionState]:
        """
        列出会话
        
        Args:
            filters: 过滤条件
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            会话列表
        """
        pass
    
    @abstractmethod
    async def exists(self, session_id: str) -> bool:
        """
        检查会话是否存在
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否存在
        """
        pass


class ISnapshotRepository(ABC):
    """快照仓库接口"""
    
    @abstractmethod
    async def save(self, snapshot: SessionSnapshot) -> bool:
        """
        保存快照
        
        Args:
            snapshot: 快照对象
            
        Returns:
            是否保存成功
        """
        pass
    
    @abstractmethod
    async def get(self, snapshot_id: str) -> Optional[SessionSnapshot]:
        """
        获取快照
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            快照对象，如果不存在则返回None
        """
        pass
    
    @abstractmethod
    async def list_by_session(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[SessionSnapshot]:
        """
        按会话列出快照
        
        Args:
            session_id: 会话ID
            limit: 返回数量限制
            
        Returns:
            快照列表
        """
        pass
    
    @abstractmethod
    async def delete(self, snapshot_id: str) -> bool:
        """
        删除快照
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    async def exists(self, snapshot_id: str) -> bool:
        """
        检查快照是否存在
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            是否存在
        """
        pass


class IRollbackRepository(ABC):
    """回滚仓库接口"""
    
    @abstractmethod
    async def save_log(self, log: RollbackLog) -> bool:
        """
        保存回滚日志
        
        Args:
            log: 回滚日志
            
        Returns:
            是否保存成功
        """
        pass
    
    @abstractmethod
    async def get_logs(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[RollbackLog]:
        """
        获取回滚日志
        
        Args:
            session_id: 会话ID
            limit: 返回数量限制
            
        Returns:
            回滚日志列表
        """
        pass
    
    @abstractmethod
    async def get_latest_point(self, session_id: str) -> Optional[str]:
        """
        获取最新回滚点
        
        Args:
            session_id: 会话ID
            
        Returns:
            快照ID，如果不存在则返回None
        """
        pass