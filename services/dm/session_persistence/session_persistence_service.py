"""
会话持久化服务
提供会话状态的保存、加载、更新和删除功能
"""

import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from ...models.dm_models import GameSession
from ...models.session_persistence_models import (
    SessionState,
    NPCState,
    TimeManagerState
)
from ...data_storage.interfaces.session_persistence import ISessionRepository
from ...data_storage.interfaces import ICacheManager
from .serializer import SessionSerializer
from .session_lock import SessionLock
from .cache_keys import SessionCacheKeys
from ...core.logging import app_logger


class SessionPersistenceService:
    """会话持久化服务"""
    
    def __init__(
        self,
        session_repository: ISessionRepository,
        cache_manager: Optional[ICacheManager] = None,
        compression_enabled: bool = True
    ):
        """
        初始化会话持久化服务
        
        Args:
            session_repository: 会话仓库
            cache_manager: 缓存管理器
            compression_enabled: 是否启用压缩
        """
        self.session_repository = session_repository
        self.cache_manager = cache_manager
        self.serializer = SessionSerializer(compression_enabled=compression_enabled)
        self.logger = app_logger
    
    async def save_session(
        self,
        session: GameSession,
        save_npc_states: bool = True,
        save_memories: bool = False
    ) -> bool:
        """
        保存会话
        
        Args:
            session: 游戏会话对象
            save_npc_states: 是否保存NPC完整状态
            save_memories: 是否保存记忆数据
            
        Returns:
            是否保存成功
        """
        try:
            # 获取会话锁
            async with SessionLock(session.session_id):
                # 收集NPC状态
                npc_states = {}
                if save_npc_states:
                    npc_states = await self._collect_npc_states(session)
                
                # 收集时间管理器状态
                time_manager_state = await self._collect_time_manager_state(session)
                
                # 收集事件规则
                event_rules = await self._collect_event_rules(session)
                
                # 收集自定义DM风格
                custom_dm_styles = await self._collect_custom_dm_styles(session)
                
                # 序列化会话状态
                serialized_data = await self.serializer.serialize(
                    session=session,
                    npc_states=npc_states,
                    time_manager_state=time_manager_state,
                    event_rules=event_rules,
                    custom_dm_styles=custom_dm_styles
                )
                
                # 保存到数据库
                session_state = SessionState.from_dict(
                    await self.serializer.deserialize(serialized_data)
                )
                
                saved = await self.session_repository.save(session_state)
                
                if saved:
                    self.logger.info(f"会话保存成功: {session.session_id}")
                else:
                    self.logger.error(f"会话保存失败: {session.session_id}")
                
                return saved
                
        except Exception as e:
            self.logger.error(f"保存会话失败: {e}", exc_info=True)
            raise
    
    async def load_session(
        self,
        session_id: str,
        load_npc_states: bool = True,
        load_memories: bool = False
    ) -> Optional[GameSession]:
        """
        加载会话
        
        Args:
            session_id: 会话ID
            load_npc_states: 是否加载NPC完整状态
            load_memories: 是否加载记忆数据
            
        Returns:
            游戏会话对象，如果不存在则返回None
        """
        try:
            # 从数据库加载会话状态
            session_state = await self.session_repository.get(session_id)
            
            if not session_state:
                self.logger.warning(f"会话不存在: {session_id}")
                return None
            
            # 反序列化
            self.logger.debug(f"加载会话: {session_id}")
            
            # 转换为GameSession对象
            game_session = await self._convert_to_game_session(
                session_state,
                load_npc_states,
                load_memories
            )
            
            self.logger.info(f"会话加载成功: {session_id}")
            return game_session
            
        except Exception as e:
            self.logger.error(f"加载会话失败: {e}", exc_info=True)
            raise
    
    async def update_session(
        self,
        session: GameSession,
        update_fields: Optional[List[str]] = None
    ) -> bool:
        """
        更新会话（部分更新）
        
        Args:
            session: 游戏会话对象
            update_fields: 要更新的字段列表，None表示全部更新
            
        Returns:
            是否更新成功
        """
        try:
            # 获取会话锁
            async with SessionLock(session.session_id):
                if update_fields:
                    # 部分更新
                    updates = {}
                    if 'name' in update_fields:
                        updates['name'] = session.name
                    if 'description' in update_fields:
                        updates['description'] = session.description
                    if 'current_scene_id' in update_fields:
                        updates['current_scene_id'] = session.current_scene_id
                    if 'dm_style' in update_fields:
                        updates['dm_style'] = session.dm_style.value if hasattr(session.dm_style, 'value') else session.dm_style
                    if 'narrative_tone' in update_fields:
                        updates['narrative_tone'] = session.narrative_tone.value if hasattr(session.narrative_tone, 'value') else session.narrative_tone
                    if 'combat_detail' in update_fields:
                        updates['combat_detail'] = session.combat_detail.value if hasattr(session.combat_detail, 'value') else session.combat_detail
                    
                    updated = await self.session_repository.update(
                        session.session_id,
                        updates
                    )
                else:
                    # 完整更新
                    saved = await self.save_session(session)
                    return saved
                
                if updated:
                    self.logger.info(f"会话更新成功: {session.session_id}")
                else:
                    self.logger.error(f"会话更新失败: {session.session_id}")
                
                return updated
                
        except Exception as e:
            self.logger.error(f"更新会话失败: {e}", exc_info=True)
            raise
    
    async def delete_session(self, session_id: str) -> bool:
        """
        删除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否删除成功
        """
        try:
            # 获取会话锁
            async with SessionLock(session_id):
                deleted = await self.session_repository.delete(session_id)
                
                if deleted:
                    self.logger.info(f"会话删除成功: {session_id}")
                else:
                    self.logger.error(f"会话删除失败: {session_id}")
                
                return deleted
                
        except Exception as e:
            self.logger.error(f"删除会话失败: {e}", exc_info=True)
            raise
    
    async def list_sessions(
        self,
        dm_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[GameSession]:
        """
        列出会话
        
        Args:
            dm_id: DM ID（可选）
            campaign_id: 战役ID（可选）
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            会话列表
        """
        try:
            # 构建过滤条件
            filters = {}
            if dm_id:
                filters['dm_id'] = dm_id
            if campaign_id:
                filters['campaign_id'] = campaign_id
            
            # 从数据库获取会话列表
            session_states = await self.session_repository.list(
                filters=filters,
                limit=limit,
                offset=offset
            )
            
            # 转换为GameSession对象列表
            sessions = []
            for session_state in session_states:
                session = await self._convert_to_game_session(
                    session_state,
                    load_npc_states=False,
                    load_memories=False
                )
                if session:
                    sessions.append(session)
            
            self.logger.debug(f"列出会话: {len(sessions)} 个会话")
            return sessions
            
        except Exception as e:
            self.logger.error(f"列出会话失败: {e}", exc_info=True)
            raise
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话状态信息
        """
        try:
            session_state = await self.session_repository.get(session_id)
            
            if not session_state:
                return {
                    'session_id': session_id,
                    'exists': False
                }
            
            return {
                'session_id': session_id,
                'exists': True,
                'name': session_state.name,
                'dm_id': session_state.dm_id,
                'campaign_id': session_state.campaign_id,
                'current_time': session_state.current_time.isoformat(),
                'current_scene_id': session_state.current_scene_id,
                'player_count': len(session_state.player_characters),
                'npc_count': len(session_state.active_npcs),
                'updated_at': session_state.updated_at.isoformat(),
                'version': session_state.version
            }
            
        except Exception as e:
            self.logger.error(f"获取会话状态失败: {e}", exc_info=True)
            raise
    
    async def _collect_npc_states(
        self,
        session: GameSession
    ) -> Dict[str, NPCState]:
        """
        收集NPC状态
        
        Args:
            session: 游戏会话对象
            
        Returns:
            NPC状态字典
        """
        # 这里应该从NPC池或其他地方收集NPC状态
        # 由于现在没有直接的访问方式，返回空字典
        # TODO: 实现NPC状态收集
        return {}
    
    async def _collect_time_manager_state(
        self,
        session: GameSession
    ) -> Optional[TimeManagerState]:
        """
        收集时间管理器状态
        
        Args:
            session: 游戏会话对象
            
        Returns:
            时间管理器状态
        """
        # 这里应该从时间管理器收集状态
        # TODO: 实现时间管理器状态收集
        return None
    
    async def _collect_event_rules(
        self,
        session: GameSession
    ) -> List[Dict[str, Any]]:
        """
        收集事件规则
        
        Args:
            session: 游戏会话对象
            
        Returns:
            事件规则列表
        """
        # 这里应该从时间管理器收集事件规则
        # TODO: 实现事件规则收集
        return []
    
    async def _collect_custom_dm_styles(
        self,
        session: GameSession
    ) -> Dict[str, Dict[str, Any]]:
        """
        收集自定义DM风格
        
        Args:
            session: 游戏会话对象
            
        Returns:
            自定义DM风格字典
        """
        # 这里应该从DMAgent收集自定义DM风格
        # TODO: 实现自定义DM风格收集
        return {}
    
    async def _convert_to_game_session(
        self,
        session_state: SessionState,
        load_npc_states: bool = True,
        load_memories: bool = False
    ) -> GameSession:
        """
        转换SessionState为GameSession
        
        Args:
            session_state: 会话状态
            load_npc_states: 是否加载NPC状态
            load_memories: 是否加载记忆
            
        Returns:
            游戏会话对象
        """
        from ...models.dm_models import DMStyle, NarrativeTone, CombatDetail
        
        # 构建GameSession对象
        game_session = GameSession(
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
        
        return game_session