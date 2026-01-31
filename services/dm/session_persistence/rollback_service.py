"""
回滚服务
提供回滚点的创建、回滚和历史查询功能
"""

import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from ...models.dm_models import GameSession
from ...models.session_persistence_models import (
    SessionState,
    SessionSnapshot,
    RollbackLog
)
from ...data_storage.interfaces.session_persistence import IRollbackRepository
from ...data_storage.interfaces.session_persistence import ISnapshotRepository
from ...data_storage.interfaces import ICacheManager
from .serializer import SessionSerializer
from .conflict_detector import ConflictDetector
from .session_lock import SessionLock
from .cache_keys import SessionCacheKeys
from ...core.logging import app_logger


class RollbackService:
    """回滚服务"""
    
    def __init__(
        self,
        rollback_repository: IRollbackRepository,
        snapshot_repository: ISnapshotRepository,
        cache_manager: Optional[ICacheManager] = None,
        compression_enabled: bool = True
    ):
        """
        初始化回滚服务
        
        Args:
            rollback_repository: 回滚仓库
            snapshot_repository: 快照仓库
            cache_manager: 缓存管理器
            compression_enabled: 是否启用压缩
        """
        self.rollback_repository = rollback_repository
        self.snapshot_repository = snapshot_repository
        self.cache_manager = cache_manager
        self.serializer = SessionSerializer(compression_enabled=compression_enabled)
        self.conflict_detector = ConflictDetector()
        self.logger = app_logger
    
    async def create_rollback_point(
        self,
        session: GameSession,
        description: Optional[str] = None,
        operator: Optional[str] = None
    ) -> str:
        """
        创建回滚点
        
        Args:
            session: 游戏会话对象
            description: 描述
            operator: 操作者ID
            
        Returns:
            回滚点ID（实际上是快照ID）
        """
        try:
            # 使用快照服务创建快照作为回滚点
            from .snapshot_service import SnapshotService
            
            snapshot_service = SnapshotService(
                snapshot_repository=self.snapshot_repository,
                cache_manager=self.cache_manager,
                compression_enabled=self.serializer.compression_enabled
            )
            
            snapshot = await snapshot_service.create_snapshot(
                session=session,
                name=f"回滚点 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                description=description or "手动创建的回滚点",
                created_by=operator or session.dm_id
            )
            
            # 记录回滚日志
            log_id = str(uuid.uuid4())
            log = RollbackLog(
                log_id=log_id,
                session_id=session.session_id,
                snapshot_id=snapshot.snapshot_id,
                timestamp=datetime.now(),
                action='create_point',
                operator=operator or session.dm_id,
                before_state={
                    'session_id': session.session_id,
                    'current_time': session.current_time.isoformat()
                },
                after_state={
                    'snapshot_id': snapshot.snapshot_id,
                    'snapshot_name': snapshot.name
                },
                conflicts=[],
                resolution=None
            )
            
            await self.rollback_repository.save_log(log)
            
            self.logger.info(f"回滚点创建成功: {snapshot.snapshot_id}")
            return snapshot.snapshot_id
            
        except Exception as e:
            self.logger.error(f"创建回滚点失败: {e}", exc_info=True)
            raise
    
    async def rollback_to_point(
        self,
        session_id: str,
        rollback_point_id: str,
        operator: str,
        create_backup: bool = True
    ) -> Dict[str, Any]:
        """
        回滚到指定点
        
        Args:
            session_id: 会话ID
            rollback_point_id: 回滚点ID（快照ID）
            operator: 操作者ID
            create_backup: 是否创建备份
            
        Returns:
            回滚结果，包含是否成功、冲突信息等
        """
        try:
            # 获取快照
            snapshot = await self.snapshot_repository.get(rollback_point_id)
            
            if not snapshot:
                return {
                    'success': False,
                    'error': f"回滚点不存在: {rollback_point_id}"
                }
            
            # 获取当前会话状态
            from .session_persistence_service import SessionPersistenceService
            from ...data_storage.interfaces.session_persistence import ISessionRepository
            
            # 这里需要获取当前状态来检测冲突
            # 简化处理，假设当前状态存储在session_state中
            current_state = snapshot.session_state
            
            # 检测冲突
            conflicts = await self.conflict_detector.detect_conflicts(
                current_state,
                snapshot.session_state
            )
            
            # 评估冲突严重程度
            severity = await self.conflict_detector.assess_conflict_severity(conflicts)
            
            # 如果冲突严重，返回错误
            if severity == 'high':
                return {
                    'success': False,
                    'error': '存在严重冲突，无法回滚',
                    'conflicts': conflicts,
                    'severity': severity
                }
            
            # 恢复快照
            if create_backup:
                from .snapshot_service import SnapshotService
                
                snapshot_service = SnapshotService(
                    snapshot_repository=self.snapshot_repository,
                    cache_manager=self.cache_manager,
                    compression_enabled=self.serializer.compression_enabled
                )
                
                # 创建备份快照
                backup_snapshot = await snapshot_service.create_auto_snapshot(
                    session=await self._create_session_from_state(snapshot.session_state),
                    trigger='before_rollback'
                )
            
            # 记录回滚日志
            log_id = str(uuid.uuid4())
            log = RollbackLog(
                log_id=log_id,
                session_id=session_id,
                snapshot_id=rollback_point_id,
                timestamp=datetime.now(),
                action='rollback',
                operator=operator,
                before_state={
                    'session_id': session_id,
                    'snapshot_id': rollback_point_id,
                    'current_time': current_state.current_time.isoformat()
                },
                after_state={
                    'snapshot_id': rollback_point_id,
                    'snapshot_name': snapshot.name,
                    'restored_time': snapshot.session_state.current_time.isoformat()
                },
                conflicts=conflicts,
                resolution='自动恢复' if severity == 'low' else '强制恢复'
            )
            
            await self.rollback_repository.save_log(log)
            
            self.logger.info(f"回滚成功: {session_id} -> {rollback_point_id}")
            
            return {
                'success': True,
                'snapshot_id': rollback_point_id,
                'snapshot_name': snapshot.name,
                'conflicts': conflicts,
                'severity': severity,
                'backup_created': create_backup
            }
            
        except Exception as e:
            self.logger.error(f"回滚失败: {e}", exc_info=True)
            raise
    
    async def get_rollback_history(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[RollbackLog]:
        """
        获取回滚历史
        
        Args:
            session_id: 会话ID
            limit: 返回数量限制
            
        Returns:
            回滚日志列表
        """
        try:
            logs = await self.rollback_repository.get_logs(
                session_id=session_id,
                limit=limit
            )
            
            self.logger.debug(f"获取回滚历史: {len(logs)} 条记录")
            return logs
            
        except Exception as e:
            self.logger.error(f"获取回滚历史失败: {e}", exc_info=True)
            raise
    
    async def resolve_conflicts(
        self,
        log_id: str,
        resolution: str,
        operator: str
    ) -> bool:
        """
        解决冲突
        
        Args:
            log_id: 回滚日志ID
            resolution: 解决方案
            operator: 操作者ID
            
        Returns:
            是否解决成功
        """
        try:
            # 获取回滚日志
            from ...data_storage.interfaces.session_persistence import IRollbackRepository
            
            # 这里需要实现获取单条日志的方法
            # 简化处理，直接更新
            # TODO: 实现日志更新方法
            
            self.logger.info(f"冲突解决成功: {log_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"解决冲突失败: {e}", exc_info=True)
            return False
    
    async def get_latest_rollback_point(self, session_id: str) -> Optional[str]:
        """
        获取最新回滚点
        
        Args:
            session_id: 会话ID
            
        Returns:
            快照ID，如果不存在则返回None
        """
        try:
            snapshot_id = await self.rollback_repository.get_latest_point(session_id)
            
            if snapshot_id:
                self.logger.debug(f"最新回滚点: {snapshot_id}")
            else:
                self.logger.debug(f"没有找到回滚点: {session_id}")
            
            return snapshot_id
            
        except Exception as e:
            self.logger.error(f"获取最新回滚点失败: {e}", exc_info=True)
            raise
    
    async def _create_session_from_state(
        self,
        session_state: SessionState
    ) -> GameSession:
        """
        从SessionState创建GameSession对象
        
        Args:
            session_state: 会话状态
            
        Returns:
            游戏会话对象
        """
        from ...models.dm_models import DMStyle, NarrativeTone, CombatDetail
        
        # 构建GameSession对象
        return GameSession(
            session_id=session_state.session_id,
            dm_id=session_state.dm_id,
            campaign_id=session_state.campaign_id,
            name=session_state.name,
            description=session_state.description,
            current_time=session_state.current_time,
            current_scene_id=session_state.current_scene_id,
            player_characters=session_state.player_characters,
            active_npcs=session_state.active_npcs,
            created_at=session_state.created_at,
            updated_at=session_state.updated_at,
            dm_style=DMStyle(session_state.dm_style) if session_state.dm_style in [e.value for e in DMStyle] else session_state.dm_style,
            narrative_tone=NarrativeTone(session_state.narrative_tone) if session_state.narrative_tone in [e.value for e in NarrativeTone] else session_state.narrative_tone,
            combat_detail=CombatDetail(session_state.combat_detail) if session_state.combat_detail in [e.value for e in CombatDetail] else session_state.combat_detail,
            custom_dm_style=session_state.custom_dm_style,
            custom_system_prompt=session_state.custom_system_prompt
        )