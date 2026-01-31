"""
快照仓库实现
提供会话快照的CRUD操作
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from ..interfaces import IStorageAdapter, ICacheManager
from ..interfaces.session_persistence import ISnapshotRepository
from ...models.session_persistence_models import SessionSnapshot, SessionState
from ...core.logging import app_logger


class SnapshotRepository(ISnapshotRepository):
    """快照仓库实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ):
        """
        初始化快照仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器
        """
        self._storage = storage_adapter
        self._cache = cache_manager
        self.logger = app_logger
    
    async def save(self, snapshot: SessionSnapshot) -> bool:
        """
        保存快照
        
        Args:
            snapshot: 快照对象
            
        Returns:
            是否保存成功
        """
        try:
            # 检查是否存在
            existing = await self.exists(snapshot.snapshot_id)
            
            if existing:
                # 更新现有快照
                query = """
                MATCH (s:SessionSnapshot {snapshot_id: $snapshot_id})
                SET s.name = $name,
                    s.description = $description,
                    s.session_state_data = $session_state_data,
                    s.tags = $tags,
                    s.is_auto = $is_auto,
                    s.trigger_type = $trigger_type
                RETURN s
                """
                
                # 序列化会话状态
                session_state_data = snapshot.session_state.to_dict()
                
                params = {
                    'snapshot_id': snapshot.snapshot_id,
                    'name': snapshot.name,
                    'description': snapshot.description,
                    'session_state_data': session_state_data,
                    'tags': snapshot.tags,
                    'is_auto': snapshot.is_auto,
                    'trigger_type': snapshot.trigger_type
                }
            else:
                # 创建新快照
                query = """
                CREATE (s:SessionSnapshot {
                    id: $id,
                    snapshot_id: $snapshot_id,
                    session_id: $session_id,
                    name: $name,
                    description: $description,
                    created_at: $created_at,
                    created_by: $created_by,
                    session_state_data: $session_state_data,
                    tags: $tags,
                    is_auto: $is_auto,
                    trigger_type: $trigger_type
                })
                RETURN s
                """
                
                # 序列化会话状态
                session_state_data = snapshot.session_state.to_dict()
                
                params = {
                    'id': snapshot.snapshot_id,
                    'snapshot_id': snapshot.snapshot_id,
                    'session_id': snapshot.session_id,
                    'name': snapshot.name,
                    'description': snapshot.description,
                    'created_at': snapshot.created_at.isoformat(),
                    'created_by': snapshot.created_by,
                    'session_state_data': session_state_data,
                    'tags': snapshot.tags,
                    'is_auto': snapshot.is_auto,
                    'trigger_type': snapshot.trigger_type
                }
            
            result = await self._storage.execute_query(query, params)
            
            if not result:
                raise Exception("保存快照失败")
            
            # 清除缓存
            await self._clear_cache(snapshot.snapshot_id, snapshot.session_id)
            
            self.logger.info(f"保存快照成功: {snapshot.snapshot_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存快照失败: {e}", exc_info=True)
            raise
    
    async def get(self, snapshot_id: str) -> Optional[SessionSnapshot]:
        """
        获取快照
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            快照对象，如果不存在则返回None
        """
        try:
            # 先从缓存获取
            if self._cache:
                from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
                cached_data = await self._cache.get(
                    SessionCacheKeys.snapshot_key(snapshot_id)
                )
                if cached_data:
                    return SessionSnapshot.from_dict(cached_data)
            
            # 从数据库获取
            query = """
            MATCH (s:SessionSnapshot {snapshot_id: $snapshot_id})
            RETURN s
            """
            
            result = await self._storage.execute_query(
                query,
                {"snapshot_id": snapshot_id}
            )
            
            if not result:
                return None
            
            snapshot_data = result[0]['s']
            snapshot = self._create_snapshot_from_data(snapshot_data)
            
            # 缓存结果
            if self._cache and snapshot:
                from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
                await self._cache.set(
                    SessionCacheKeys.snapshot_key(snapshot_id),
                    snapshot.to_dict(),
                    ttl=1800  # 30分钟
                )
            
            return snapshot
            
        except Exception as e:
            self.logger.error(f"获取快照失败: {e}", exc_info=True)
            raise
    
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
        try:
            # 先从缓存获取
            if self._cache:
                from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
                cached_list = await self._cache.get(
                    SessionCacheKeys.session_snapshots_key(session_id)
                )
                if cached_list:
                    return [SessionSnapshot.from_dict(data) for data in cached_list]
            
            # 从数据库获取
            query = """
            MATCH (s:SessionSnapshot {session_id: $session_id})
            RETURN s
            ORDER BY s.created_at DESC
            LIMIT $limit
            """
            
            result = await self._storage.execute_query(
                query,
                {"session_id": session_id, "limit": limit}
            )
            
            snapshots = []
            for record in result:
                snapshot_data = record['s']
                snapshot = self._create_snapshot_from_data(snapshot_data)
                if snapshot:
                    snapshots.append(snapshot)
            
            # 缓存结果
            if self._cache and snapshots:
                from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
                await self._cache.set(
                    SessionCacheKeys.session_snapshots_key(session_id),
                    [snap.to_dict() for snap in snapshots],
                    ttl=600  # 10分钟
                )
            
            return snapshots
            
        except Exception as e:
            self.logger.error(f"列出快照失败: {e}", exc_info=True)
            raise
    
    async def delete(self, snapshot_id: str) -> bool:
        """
        删除快照
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            是否删除成功
        """
        try:
            # 先获取快照以获取session_id
            snapshot = await self.get(snapshot_id)
            if not snapshot:
                return False
            
            query = """
            MATCH (s:SessionSnapshot {snapshot_id: $snapshot_id})
            DETACH DELETE s
            """
            
            await self._storage.execute_query(query, {"snapshot_id": snapshot_id})
            
            # 清除缓存
            await self._clear_cache(snapshot_id, snapshot.session_id)
            
            self.logger.info(f"删除快照成功: {snapshot_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除快照失败: {e}", exc_info=True)
            return False
    
    async def exists(self, snapshot_id: str) -> bool:
        """
        检查快照是否存在
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            是否存在
        """
        try:
            query = """
            MATCH (s:SessionSnapshot {snapshot_id: $snapshot_id})
            RETURN count(s) as count
            """
            
            result = await self._storage.execute_query(
                query,
                {"snapshot_id": snapshot_id}
            )
            
            return result[0]['count'] > 0 if result else False
            
        except Exception as e:
            self.logger.error(f"检查快照存在性失败: {e}", exc_info=True)
            return False
    
    def _create_snapshot_from_data(
        self,
        data: Dict[str, Any]
    ) -> Optional[SessionSnapshot]:
        """
        从数据库数据创建SessionSnapshot对象
        
        Args:
            data: 数据库数据
            
        Returns:
            SessionSnapshot对象
        """
        try:
            # 从session_state_data重建SessionState
            session_state_data = data.get('session_state_data', {})
            session_state = SessionState.from_dict(session_state_data)
            
            return SessionSnapshot(
                snapshot_id=data.get('snapshot_id'),
                session_id=data.get('session_id'),
                name=data.get('name', ''),
                description=data.get('description'),
                created_at=datetime.fromisoformat(data.get('created_at')),
                created_by=data.get('created_by'),
                session_state=session_state,
                tags=data.get('tags', []),
                is_auto=data.get('is_auto', False),
                trigger_type=data.get('trigger_type', 'manual')
            )
        except Exception as e:
            self.logger.error(f"创建快照对象失败: {e}", exc_info=True)
            return None
    
    async def _clear_cache(self, snapshot_id: str, session_id: str) -> None:
        """
        清除缓存
        
        Args:
            snapshot_id: 快照ID
            session_id: 会话ID
        """
        if not self._cache:
            return
        
        from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
        
        # 清除快照缓存
        await self._cache.delete(
            SessionCacheKeys.snapshot_key(snapshot_id)
        )
        
        # 清除会话快照列表缓存
        await self._cache.delete(
            SessionCacheKeys.session_snapshots_key(session_id)
        )