"""
会话仓库实现
提供会话状态的CRUD操作
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..interfaces import IStorageAdapter, ICacheManager
from ..interfaces.session_persistence import ISessionRepository
from ...models.session_persistence_models import SessionState
from ...core.logging import app_logger


class SessionRepository(ISessionRepository):
    """会话仓库实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ):
        """
        初始化会话仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器
        """
        self._storage = storage_adapter
        self._cache = cache_manager
        self.logger = app_logger
    
    async def save(self, session_state: SessionState) -> bool:
        """
        保存会话状态
        
        Args:
            session_state: 会话状态
            
        Returns:
            是否保存成功
        """
        try:
            # 构建节点数据
            node_data = {
                'id': session_state.session_id,
                'session_id': session_state.session_id,
                'dm_id': session_state.dm_id,
                'campaign_id': session_state.campaign_id,
                'name': session_state.name,
                'description': session_state.description,
                'current_time': session_state.current_time.isoformat(),
                'created_at': session_state.created_at.isoformat(),
                'updated_at': session_state.updated_at.isoformat(),
                'dm_style': session_state.dm_style,
                'narrative_tone': session_state.narrative_tone,
                'combat_detail': session_state.combat_detail,
                'custom_dm_style': session_state.custom_dm_style,
                'custom_system_prompt': session_state.custom_system_prompt,
                'version': session_state.version,
                'checksum': session_state.checksum
            }
            
            # 检查是否存在
            existing = await self.exists(session_state.session_id)
            
            if existing:
                # 更新现有会话
                query = """
                MATCH (s:GameSession {session_id: $session_id})
                SET s.dm_id = $dm_id,
                    s.campaign_id = $campaign_id,
                    s.name = $name,
                    s.description = $description,
                    s.current_time = $current_time,
                    s.updated_at = $updated_at,
                    s.current_scene_id = $current_scene_id,
                    s.player_characters = $player_characters,
                    s.active_npcs = $active_npcs,
                    s.dm_style = $dm_style,
                    s.narrative_tone = $narrative_tone,
                    s.combat_detail = $combat_detail,
                    s.custom_dm_style = $custom_dm_style,
                    s.custom_system_prompt = $custom_system_prompt,
                    s.version = $version,
                    s.checksum = $checksum
                RETURN s
                """
                
                params = {
                    'session_id': session_state.session_id,
                    'dm_id': session_state.dm_id,
                    'campaign_id': session_state.campaign_id,
                    'name': session_state.name,
                    'description': session_state.description,
                    'current_time': session_state.current_time.isoformat(),
                    'updated_at': datetime.now().isoformat(),
                    'current_scene_id': session_state.current_scene_id,
                    'player_characters': session_state.player_characters,
                    'active_npcs': session_state.active_npcs,
                    'dm_style': session_state.dm_style,
                    'narrative_tone': session_state.narrative_tone,
                    'combat_detail': session_state.combat_detail,
                    'custom_dm_style': session_state.custom_dm_style,
                    'custom_system_prompt': session_state.custom_system_prompt,
                    'version': session_state.version,
                    'checksum': session_state.checksum
                }
            else:
                # 创建新会话
                query = """
                CREATE (s:GameSession {
                    id: $id,
                    session_id: $session_id,
                    dm_id: $dm_id,
                    campaign_id: $campaign_id,
                    name: $name,
                    description: $description,
                    current_time: $current_time,
                    created_at: $created_at,
                    updated_at: $updated_at,
                    current_scene_id: $current_scene_id,
                    player_characters: $player_characters,
                    active_npcs: $active_npcs,
                    dm_style: $dm_style,
                    narrative_tone: $narrative_tone,
                    combat_detail: $combat_detail,
                    custom_dm_style: $custom_dm_style,
                    custom_system_prompt: $custom_system_prompt,
                    version: $version,
                    checksum: $checksum
                })
                RETURN s
                """
                
                params = {
                    'id': session_state.session_id,
                    'session_id': session_state.session_id,
                    'dm_id': session_state.dm_id,
                    'campaign_id': session_state.campaign_id,
                    'name': session_state.name,
                    'description': session_state.description,
                    'current_time': session_state.current_time.isoformat(),
                    'created_at': session_state.created_at.isoformat(),
                    'updated_at': session_state.updated_at.isoformat(),
                    'current_scene_id': session_state.current_scene_id,
                    'player_characters': session_state.player_characters,
                    'active_npcs': session_state.active_npcs,
                    'dm_style': session_state.dm_style,
                    'narrative_tone': session_state.narrative_tone,
                    'combat_detail': session_state.combat_detail,
                    'custom_dm_style': session_state.custom_dm_style,
                    'custom_system_prompt': session_state.custom_system_prompt,
                    'version': session_state.version,
                    'checksum': session_state.checksum
                }
            
            result = await self._storage.execute_query(query, params)
            
            if not result:
                raise Exception("保存会话失败")
            
            # 清除缓存
            await self._clear_cache(session_state.session_id)
            
            self.logger.info(f"保存会话成功: {session_state.session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存会话失败: {e}", exc_info=True)
            raise
    
    async def get(self, session_id: str) -> Optional[SessionState]:
        """
        获取会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话状态，如果不存在则返回None
        """
        try:
            # 先从缓存获取
            if self._cache:
                from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
                cached_data = await self._cache.get(
                    SessionCacheKeys.session_state_key(session_id)
                )
                if cached_data:
                    return SessionState.from_dict(cached_data)
            
            # 从数据库获取
            query = """
            MATCH (s:GameSession {session_id: $session_id})
            RETURN s
            """
            
            result = await self._storage.execute_query(
                query,
                {"session_id": session_id}
            )
            
            if not result:
                return None
            
            session_data = result[0]['s']
            session_state = self._create_session_state_from_data(session_data)
            
            # 缓存结果
            if self._cache and session_state:
                from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
                await self._cache.set(
                    SessionCacheKeys.session_state_key(session_id),
                    session_state.to_dict(),
                    ttl=300  # 5分钟
                )
            
            return session_state
            
        except Exception as e:
            self.logger.error(f"获取会话失败: {e}", exc_info=True)
            raise
    
    async def update(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新会话状态（部分更新）
        
        Args:
            session_id: 会话ID
            updates: 要更新的字段字典
            
        Returns:
            是否更新成功
        """
        try:
            if not updates:
                return True
            
            # 添加更新时间
            updates['updated_at'] = datetime.now().isoformat()
            
            # 构建SET子句
            set_clauses = [f"s.{k} = ${k}" for k in updates.keys()]
            query = f"""
            MATCH (s:GameSession {{session_id: $session_id}})
            SET {', '.join(set_clauses)}
            RETURN s
            """
            
            params = {"session_id": session_id, **updates}
            
            result = await self._storage.execute_query(query, params)
            
            if not result:
                return False
            
            # 清除缓存
            await self._clear_cache(session_id)
            
            self.logger.debug(f"更新会话成功: {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"更新会话失败: {e}", exc_info=True)
            return False
    
    async def delete(self, session_id: str) -> bool:
        """
        删除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否删除成功
        """
        try:
            query = """
            MATCH (s:GameSession {session_id: $session_id})
            DETACH DELETE s
            """
            
            await self._storage.execute_query(query, {"session_id": session_id})
            
            # 清除缓存
            await self._clear_cache(session_id)
            
            self.logger.info(f"删除会话成功: {session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"删除会话失败: {e}", exc_info=True)
            return False
    
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
        try:
            query_parts = ["MATCH (s:GameSession)"]
            where_conditions = []
            params = {}
            
            # 添加过滤条件
            if filters.get('dm_id'):
                where_conditions.append("s.dm_id = $dm_id")
                params['dm_id'] = filters['dm_id']
            
            if filters.get('campaign_id'):
                where_conditions.append("s.campaign_id = $campaign_id")
                params['campaign_id'] = filters['campaign_id']
            
            # 添加WHERE子句
            if where_conditions:
                query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            # 添加排序和分页
            query_parts.append("ORDER BY s.updated_at DESC")
            query_parts.append("LIMIT $limit")
            query_parts.append("SKIP $offset")
            
            query = " ".join(query_parts) + " RETURN s"
            params['limit'] = limit
            params['offset'] = offset
            
            result = await self._storage.execute_query(query, params)
            
            sessions = []
            for record in result:
                session_data = record['s']
                session_state = self._create_session_state_from_data(session_data)
                if session_state:
                    sessions.append(session_state)
            
            return sessions
            
        except Exception as e:
            self.logger.error(f"列出会话失败: {e}", exc_info=True)
            raise
    
    async def exists(self, session_id: str) -> bool:
        """
        检查会话是否存在
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否存在
        """
        try:
            query = """
            MATCH (s:GameSession {session_id: $session_id})
            RETURN count(s) as count
            """
            
            result = await self._storage.execute_query(
                query,
                {"session_id": session_id}
            )
            
            return result[0]['count'] > 0 if result else False
            
        except Exception as e:
            self.logger.error(f"检查会话存在性失败: {e}", exc_info=True)
            return False
    
    def _create_session_state_from_data(
        self,
        data: Dict[str, Any]
    ) -> SessionState:
        """
        从数据库数据创建SessionState对象
        
        Args:
            data: 数据库数据
            
        Returns:
            SessionState对象
        """
        from ...models.session_persistence_models import (
            NPCState,
            TimeManagerState
        )
        
        # 这里需要构建完整的SessionState对象
        # 由于数据库中可能只存储了部分数据，这里需要补充默认值
        return SessionState(
            session_id=data.get('session_id'),
            dm_id=data.get('dm_id'),
            campaign_id=data.get('campaign_id'),
            name=data.get('name', ''),
            description=data.get('description', ''),
            current_time=datetime.fromisoformat(data.get('current_time')),
            created_at=datetime.fromisoformat(data.get('created_at')),
            updated_at=datetime.fromisoformat(data.get('updated_at')),
            current_scene_id=data.get('current_scene_id'),
            player_characters=data.get('player_characters', []),
            active_npcs=data.get('active_npcs', []),
            dm_style=data.get('dm_style', 'balanced'),
            narrative_tone=data.get('narrative_tone', 'descriptive'),
            combat_detail=data.get('combat_detail', 'normal'),
            custom_dm_style=data.get('custom_dm_style'),
            custom_system_prompt=data.get('custom_system_prompt'),
            npc_states={},
            time_manager_state=TimeManagerState(
                current_time=datetime.fromisoformat(data.get('current_time')),
                session_time_start=datetime.fromisoformat(data.get('created_at')),
                registered_events=[]
            ),
            event_rules=[],
            custom_dm_styles={},
            version=data.get('version', '1.0.0'),
            checksum=data.get('checksum')
        )
    
    async def _clear_cache(self, session_id: str) -> None:
        """
        清除缓存
        
        Args:
            session_id: 会话ID
        """
        if not self._cache:
            return
        
        from ...services.dm.session_persistence.cache_keys import SessionCacheKeys
        
        # 清除会话状态缓存
        await self._cache.delete(
            SessionCacheKeys.session_state_key(session_id)
        )