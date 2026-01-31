"""
回滚仓库实现
提供回滚日志的CRUD操作
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from ..interfaces import IStorageAdapter, ICacheManager
from ..interfaces.session_persistence import IRollbackRepository
from ...models.session_persistence_models import RollbackLog
from ...core.logging import app_logger


class RollbackRepository(IRollbackRepository):
    """回滚仓库实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ):
        """
        初始化回滚仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器
        """
        self._storage = storage_adapter
        self._cache = cache_manager
        self.logger = app_logger
    
    async def save_log(self, log: RollbackLog) -> bool:
        """
        保存回滚日志
        
        Args:
            log: 回滚日志
            
        Returns:
            是否保存成功
        """
        try:
            query = """
            CREATE (r:RollbackLog {
                id: $id,
                log_id: $log_id,
                session_id: $session_id,
                snapshot_id: $snapshot_id,
                timestamp: $timestamp,
                action: $action,
                operator: $operator,
                before_state: $before_state,
                after_state: $after_state,
                conflicts: $conflicts,
                resolution: $resolution
            })
            RETURN r
            """
            
            params = {
                'id': log.log_id,
                'log_id': log.log_id,
                'session_id': log.session_id,
                'snapshot_id': log.snapshot_id,
                'timestamp': log.timestamp.isoformat(),
                'action': log.action,
                'operator': log.operator,
                'before_state': log.before_state,
                'after_state': log.after_state,
                'conflicts': log.conflicts,
                'resolution': log.resolution
            }
            
            result = await self._storage.execute_query(query, params)
            
            if not result:
                raise Exception("保存回滚日志失败")
            
            # 清除缓存
            await self._clear_cache(log.session_id)
            
            self.logger.info(f"保存回滚日志成功: {log.log_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存回滚日志失败: {e}", exc_info=True)
            raise
    
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
        try:
            # 先从缓存获取
            if self._cache:
                from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
                cached_list = await self._cache.get(
                    SessionCacheKeys.rollback_logs_key(session_id)
                )
                if cached_list:
                    return [RollbackLog.from_dict(data) for data in cached_list]
            
            # 从数据库获取
            query = """
            MATCH (r:RollbackLog {session_id: $session_id})
            RETURN r
            ORDER BY r.timestamp DESC
            LIMIT $limit
            """
            
            result = await self._storage.execute_query(
                query,
                {"session_id": session_id, "limit": limit}
            )
            
            logs = []
            for record in result:
                log_data = record['r']
                log = self._create_log_from_data(log_data)
                if log:
                    logs.append(log)
            
            # 缓存结果
            if self._cache and logs:
                from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
                await self._cache.set(
                    SessionCacheKeys.rollback_logs_key(session_id),
                    [log.to_dict() for log in logs],
                    ttl=600  # 10分钟
                )
            
            return logs
            
        except Exception as e:
            self.logger.error(f"获取回滚日志失败: {e}", exc_info=True)
            raise
    
    async def get_latest_point(self, session_id: str) -> Optional[str]:
        """
        获取最新回滚点
        
        Args:
            session_id: 会话ID
            
        Returns:
            快照ID，如果不存在则返回None
        """
        try:
            query = """
            MATCH (r:RollbackLog {session_id: $session_id})
            WHERE r.action = 'create_point'
            RETURN r.snapshot_id as snapshot_id
            ORDER BY r.timestamp DESC
            LIMIT 1
            """
            
            result = await self._storage.execute_query(
                query,
                {"session_id": session_id}
            )
            
            if result and result[0]['snapshot_id']:
                return result[0]['snapshot_id']
            
            return None
            
        except Exception as e:
            self.logger.error(f"获取最新回滚点失败: {e}", exc_info=True)
            return None
    
    def _create_log_from_data(
        self,
        data: Dict[str, Any]
    ) -> Optional[RollbackLog]:
        """
        从数据库数据创建RollbackLog对象
        
        Args:
            data: 数据库数据
            
        Returns:
            RollbackLog对象
        """
        try:
            return RollbackLog(
                log_id=data.get('log_id'),
                session_id=data.get('session_id'),
                snapshot_id=data.get('snapshot_id'),
                timestamp=datetime.fromisoformat(data.get('timestamp')),
                action=data.get('action'),
                operator=data.get('operator'),
                before_state=data.get('before_state', {}),
                after_state=data.get('after_state', {}),
                conflicts=data.get('conflicts', []),
                resolution=data.get('resolution')
            )
        except Exception as e:
            self.logger.error(f"创建回滚日志对象失败: {e}", exc_info=True)
            return None
    
    async def _clear_cache(self, session_id: str) -> None:
        """
        清除缓存
        
        Args:
            session_id: 会话ID
        """
        if not self._cache:
            return
        
        from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
        
        # 清除回滚日志缓存
        await self._cache.delete(
            SessionCacheKeys.rollback_logs_key(session_id)
        )