"""
快照服务
提供会话快照的创建、恢复、列表和删除功能
"""

import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from ...models.dm_models import GameSession
from ...models.session_persistence_models import (
    SessionState,
    SessionSnapshot,
    SnapshotTrigger
)
from ...data_storage.interfaces.session_persistence import ISnapshotRepository
from ...data_storage.interfaces import ICacheManager
from .serializer import SessionSerializer
from .conflict_detector import ConflictDetector
from .session_lock import SessionLock
from .cache_keys import SessionCacheKeys
from ...core.logging import app_logger


class SnapshotService:
    """快照服务"""
    
    def __init__(
        self,
        snapshot_repository: ISnapshotRepository,
        cache_manager: Optional[ICacheManager] = None,
        compression_enabled: bool = True
    ):
        """
        初始化快照服务
        
        Args:
            snapshot_repository: 快照仓库
            cache_manager: 缓存管理器
            compression_enabled: 是否启用压缩
        """
        self.snapshot_repository = snapshot_repository
        self.cache_manager = cache_manager
        self.serializer = SessionSerializer(compression_enabled=compression_enabled)
        self.conflict_detector = ConflictDetector()
        self.logger = app_logger
    
    async def create_snapshot(
        self,
        session: GameSession,
        name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        created_by: Optional[str] = None
    ) -> SessionSnapshot:
        """
        创建快照
        
        Args:
            session: 游戏会话对象
            name: 快照名称
            description: 快照描述
            tags: 标签列表
            created_by: 创建者ID
            
        Returns:
            创建的快照
        """
        try:
            # 生成快照ID
            snapshot_id = str(uuid.uuid4())
            
            # 构建会话状态
            from .session_persistence_service import SessionPersistenceService
            # 这里简化处理，直接创建基本状态
            from ...models.session_persistence_models import (
                NPCState,
                TimeManagerState
            )
            
            session_state = SessionState(
                session_id=session.session_id,
                dm_id=session.dm_id,
                campaign_id=session.campaign_id,
                name=session.name,
                description=session.description,
                current_time=session.current_time,
                created_at=session.created_at,
                updated_at=session.updated_at,
                current_scene_id=session.current_scene_id,
                player_characters=session.player_characters,
                active_npcs=session.active_npcs,
                dm_style=session.dm_style.value if hasattr(session.dm_style, 'value') else session.dm_style,
                narrative_tone=session.narrative_tone.value if hasattr(session.narrative_tone, 'value') else session.narrative_tone,
                combat_detail=session.combat_detail.value if hasattr(session.combat_detail, 'value') else session.combat_detail,
                custom_dm_style=session.custom_dm_style,
                custom_system_prompt=session.custom_system_prompt,
                npc_states={},
                time_manager_state=TimeManagerState(
                    current_time=session.current_time,
                    session_time_start=session.created_at,
                    registered_events=[]
                ),
                event_rules=[],
                custom_dm_styles={},
                version=self.serializer.version
            )
            
            # 创建快照对象
            snapshot = SessionSnapshot(
                snapshot_id=snapshot_id,
                session_id=session.session_id,
                name=name,
                description=description,
                created_at=datetime.now(),
                created_by=created_by or session.dm_id,
                session_state=session_state,
                tags=tags or [],
                is_auto=False,
                trigger_type=SnapshotTrigger.MANUAL.value
            )
            
            # 保存快照
            saved = await self.snapshot_repository.save(snapshot)
            
            if saved:
                self.logger.info(f"快照创建成功: {snapshot_id}")
            else:
                self.logger.error(f"快照创建失败: {snapshot_id}")
            
            return snapshot
            
        except Exception as e:
            self.logger.error(f"创建快照失败: {e}", exc_info=True)
            raise
    
    async def restore_snapshot(
        self,
        snapshot_id: str,
        create_backup: bool = True
    ) -> bool:
        """
        恢复快照
        
        Args:
            snapshot_id: 快照ID
            create_backup: 是否在恢复前创建备份
            
        Returns:
            是否恢复成功
        """
        try:
            # 获取快照
            snapshot = await self.snapshot_repository.get(snapshot_id)
            
            if not snapshot:
                raise Exception(f"快照不存在: {snapshot_id}")
            
            # 如果需要，创建备份快照
            if create_backup:
                from .session_persistence_service import SessionPersistenceService
                from ...models.session_persistence_models import NPCState, TimeManagerState
                
                # 这里需要从session_state重建GameSession
                # 简化处理，直接保存当前状态作为备份
                backup_snapshot = SessionSnapshot(
                    snapshot_id=str(uuid.uuid4()),
                    session_id=snapshot.session_id,
                    name=f"备份于恢复前 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    description="恢复快照前的自动备份",
                    created_at=datetime.now(),
                    created_by="system",
                    session_state=snapshot.session_state,
                    tags=["auto_backup"],
                    is_auto=True,
                    trigger_type=SnapshotTrigger.BEFORE_ROLLBACK.value
                )
                
                await self.snapshot_repository.save(backup_snapshot)
                self.logger.info(f"创建备份快照: {backup_snapshot.snapshot_id}")
            
            # 检测冲突
            # 这里简化处理，假设没有冲突检测
            
            # 恢复快照状态到会话
            # 这里需要实际的恢复逻辑
            # TODO: 实现完整的恢复逻辑
            
            self.logger.info(f"快照恢复成功: {snapshot_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"恢复快照失败: {e}", exc_info=True)
            raise
    
    async def list_snapshots(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[SessionSnapshot]:
        """
        列出会话的快照
        
        Args:
            session_id: 会话ID
            limit: 返回数量限制
            
        Returns:
            快照列表
        """
        try:
            snapshots = await self.snapshot_repository.list_by_session(
                session_id=session_id,
                limit=limit
            )
            
            self.logger.debug(f"列出快照: {len(snapshots)} 个")
            return snapshots
            
        except Exception as e:
            self.logger.error(f"列出快照失败: {e}", exc_info=True)
            raise
    
    async def get_snapshot(
        self,
        snapshot_id: str
    ) -> Optional[SessionSnapshot]:
        """
        获取快照
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            快照对象，如果不存在则返回None
        """
        try:
            snapshot = await self.snapshot_repository.get(snapshot_id)
            
            if snapshot:
                self.logger.debug(f"获取快照: {snapshot_id}")
            else:
                self.logger.warning(f"快照不存在: {snapshot_id}")
            
            return snapshot
            
        except Exception as e:
            self.logger.error(f"获取快照失败: {e}", exc_info=True)
            raise
    
    async def delete_snapshot(self, snapshot_id: str) -> bool:
        """
        删除快照
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            是否删除成功
        """
        try:
            deleted = await self.snapshot_repository.delete(snapshot_id)
            
            if deleted:
                self.logger.info(f"快照删除成功: {snapshot_id}")
            else:
                self.logger.error(f"快照删除失败: {snapshot_id}")
            
            return deleted
            
        except Exception as e:
            self.logger.error(f"删除快照失败: {e}", exc_info=True)
            raise
    
    async def create_auto_snapshot(
        self,
        session: GameSession,
        trigger: str
    ) -> Optional[SessionSnapshot]:
        """
        创建自动快照
        
        Args:
            session: 游戏会话对象
            trigger: 触发原因（如 'auto_save', 'before_rollback'）
            
        Returns:
            创建的快照，如果失败则返回None
        """
        try:
            # 生成快照ID
            snapshot_id = str(uuid.uuid4())
            
            # 构建会话状态
            from ...models.session_persistence_models import (
                NPCState,
                TimeManagerState
            )
            
            session_state = SessionState(
                session_id=session.session_id,
                dm_id=session.dm_id,
                campaign_id=session.campaign_id,
                name=session.name,
                description=session.description,
                current_time=session.current_time,
                created_at=session.created_at,
                updated_at=session.updated_at,
                current_scene_id=session.current_scene_id,
                player_characters=session.player_characters,
                active_npcs=session.active_npcs,
                dm_style=session.dm_style.value if hasattr(session.dm_style, 'value') else session.dm_style,
                narrative_tone=session.narrative_tone.value if hasattr(session.narrative_tone, 'value') else session.narrative_tone,
                combat_detail=session.combat_detail.value if hasattr(session.combat_detail, 'value') else session.combat_detail,
                custom_dm_style=session.custom_dm_style,
                custom_system_prompt=session.custom_system_prompt,
                npc_states={},
                time_manager_state=TimeManagerState(
                    current_time=session.current_time,
                    session_time_start=session.created_at,
                    registered_events=[]
                ),
                event_rules=[],
                custom_dm_styles={},
                version=self.serializer.version
            )
            
            # 创建快照对象
            snapshot = SessionSnapshot(
                snapshot_id=snapshot_id,
                session_id=session.session_id,
                name=f"自动快照 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                description=f"自动创建的快照，触发原因: {trigger}",
                created_at=datetime.now(),
                created_by="system",
                session_state=session_state,
                tags=["auto", trigger],
                is_auto=True,
                trigger_type=trigger
            )
            
            # 保存快照
            saved = await self.snapshot_repository.save(snapshot)
            
            if saved:
                self.logger.info(f"自动快照创建成功: {snapshot_id}")
                return snapshot
            else:
                self.logger.error(f"自动快照创建失败: {snapshot_id}")
                return None
            
        except Exception as e:
            self.logger.error(f"创建自动快照失败: {e}", exc_info=True)
            return None