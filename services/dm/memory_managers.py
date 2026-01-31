"""
记忆管理系统
实现场景记忆、历史记忆、NPC记忆的持久化和检索机制
"""

import logging
import uuid
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict

from ...models.dm_models import (
    SceneMemory,
    HistoryMemory,
    NPCMemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
    DispatchedTask,
    NPCResponse,
    GameEvent,
    InputType
)
from ...data_storage.interfaces import IMemoryRepository, ICacheManager
from ...provider import ProviderManager, ProviderRequest, ChatMessage
from ...core.logging import app_logger


# ==================== 缓存键生成器 ====================

class CacheKeyGenerator:
    """缓存键生成器"""
    
    @staticmethod
    def scene_memory_key(session_id: str, scene_id: Optional[str] = None) -> str:
        """生成场景记忆缓存键"""
        if scene_id:
            return f"scene_memory:{session_id}:{scene_id}"
        return f"scene_memory:{session_id}"
    
    @staticmethod
    def history_memory_key(session_id: str) -> str:
        """生成历史记忆缓存键"""
        return f"history_memory:{session_id}"
    
    @staticmethod
    def npc_memory_key(npc_id: str, session_id: Optional[str] = None) -> str:
        """生成NPC记忆缓存键"""
        if session_id:
            return f"npc_memory:{npc_id}:{session_id}"
        return f"npc_memory:{npc_id}"
    
    @staticmethod
    def search_cache_key(query: MemorySearchQuery) -> str:
        """生成搜索缓存键"""
        query_hash = hash(json.dumps(query.to_dict(), sort_keys=True))
        return f"memory_search:{query.session_id}:{query_hash}"


# ==================== 场景记忆管理器 ====================

class SceneMemoryManager:
    """场景记忆管理器"""
    
    def __init__(
        self,
        memory_repository: IMemoryRepository,
        cache_manager: Optional[ICacheManager] = None,
        cache_ttl: int = 300
    ):
        """
        初始化场景记忆管理器
        
        Args:
            memory_repository: 记忆仓库
            cache_manager: 缓存管理器（可选）
            cache_ttl: 缓存有效期（秒）
        """
        self.memory_repository = memory_repository
        self.cache_manager = cache_manager
        self.cache_ttl = cache_ttl
        self.logger = app_logger
    
    async def record_event(
        self,
        session_id: str,
        scene_id: str,
        event_type: str,
        description: str,
        involved_entities: Optional[List[str]] = None,
        state_changes: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        importance: float = 0.5
    ) -> SceneMemory:
        """
        记录场景事件
        
        Args:
            session_id: 会话ID
            scene_id: 场景ID
            event_type: 事件类型（state_change, interaction, environment, discovery）
            description: 事件描述
            involved_entities: 涉及的实体ID列表
            state_changes: 状态变化
            tags: 标签列表
            importance: 重要性 0-1
            
        Returns:
            SceneMemory: 创建的场景记忆
        """
        memory = SceneMemory(
            memory_id=str(uuid.uuid4()),
            session_id=session_id,
            scene_id=scene_id,
            event_type=event_type,
            timestamp=datetime.now(),
            description=description,
            involved_entities=involved_entities or [],
            state_changes=state_changes or {},
            related_scene_ids=[],
            importance=min(max(importance, 0.0), 1.0),
            tags=tags or []
        )
        
        # 保存到数据库
        await self.memory_repository.save_scene_memory(memory)
        
        # 清除缓存
        await self._clear_cache(session_id, scene_id)
        
        self.logger.debug(
            f"记录场景事件: {session_id}/{scene_id} - {event_type}"
        )
        
        return memory
    
    async def get_scene_memories(
        self,
        session_id: str,
        scene_id: Optional[str] = None,
        use_cache: bool = True
    ) -> List[SceneMemory]:
        """
        获取场景记忆
        
        Args:
            session_id: 会话ID
            scene_id: 场景ID（可选，不指定则获取整个会话的场景记忆）
            use_cache: 是否使用缓存
            
        Returns:
            List[SceneMemory]: 场景记忆列表
        """
        cache_key = CacheKeyGenerator.scene_memory_key(session_id, scene_id)
        
        # 尝试从缓存获取
        if use_cache and self.cache_manager:
            cached = await self.cache_manager.get(cache_key)
            if cached:
                return cached
        
        # 从数据库获取
        memories = await self.memory_repository.get_scene_memories(
            session_id=session_id,
            scene_id=scene_id
        )
        
        # 缓存结果
        if use_cache and self.cache_manager and memories:
            await self.cache_manager.set(
                cache_key,
                memories,
                ttl=self.cache_ttl
            )
        
        return memories
    
    async def get_related_scenes(
        self,
        session_id: str,
        scene_id: str,
        max_depth: int = 2
    ) -> List[str]:
        """
        获取相关场景
        
        Args:
            session_id: 会话ID
            scene_id: 场景ID
            max_depth: 最大关联深度
            
        Returns:
            List[str]: 相关场景ID列表
        """
        memories = await self.get_scene_memories(session_id, scene_id)
        related = set()
        
        for memory in memories:
            related.update(memory.related_scene_ids)
        
        return list(related)
    
    async def link_scenes(
        self,
        session_id: str,
        from_scene_id: str,
        to_scene_id: str,
        description: str
    ) -> None:
        """
        建立场景关联
        
        Args:
            session_id: 会话ID
            from_scene_id: 源场景ID
            to_scene_id: 目标场景ID
            description: 关联描述
        """
        # 在两个场景都记录关联
        for scene_id in [from_scene_id, to_scene_id]:
            memories = await self.get_scene_memories(session_id, scene_id)
            for memory in memories:
                if to_scene_id not in memory.related_scene_ids and scene_id == from_scene_id:
                    memory.related_scene_ids.append(to_scene_id)
                    await self.memory_repository.save_scene_memory(memory)
        
        self.logger.debug(
            f"建立场景关联: {from_scene_id} <-> {to_scene_id}"
        )
    
    async def _clear_cache(self, session_id: str, scene_id: Optional[str] = None) -> None:
        """清除缓存"""
        if not self.cache_manager:
            return
        
        cache_key = CacheKeyGenerator.scene_memory_key(session_id, scene_id)
        await self.cache_manager.delete(cache_key)


# ==================== 历史记忆管理器 ====================

class HistoryMemoryManager:
    """历史记忆管理器"""
    
    def __init__(
        self,
        memory_repository: IMemoryRepository,
        model_scheduler: Optional[ProviderManager] = None,
        cache_manager: Optional[ICacheManager] = None,
        cache_ttl: int = 300
    ):
        """
        初始化历史记忆管理器
        
        Args:
            memory_repository: 记忆仓库
            model_scheduler: 模型调度器（用于摘要生成）
            cache_manager: 缓存管理器（可选）
            cache_ttl: 缓存有效期（秒）
        """
        self.memory_repository = memory_repository
        self.model_scheduler = model_scheduler
        self.cache_manager = cache_manager
        self.cache_ttl = cache_ttl
        self.logger = app_logger
    
    async def record_event(
        self,
        session_id: str,
        event_type: str,
        content: str,
        participants: Optional[List[str]] = None,
        location: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> HistoryMemory:
        """
        记录历史事件
        
        Args:
            session_id: 会话ID
            event_type: 事件类型（player_action, npc_response, dm_narration, system_event）
            content: 事件内容
            participants: 参与者ID列表
            location: 地点（场景ID）
            tags: 标签列表
            importance: 重要性 0-1
            metadata: 元数据
            
        Returns:
            HistoryMemory: 创建的历史记忆
        """
        memory = HistoryMemory(
            memory_id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=datetime.now(),
            event_type=event_type,
            content=content,
            participants=participants or [],
            location=location,
            summary="",  # 将异步生成
            importance=min(max(importance, 0.0), 1.0),
            tags=tags or [],
            metadata=metadata or {}
        )
        
        # 生成摘要
        memory.summary = await self._generate_summary(memory)
        
        # 保存到数据库
        await self.memory_repository.save_history_memory(memory)
        
        # 清除缓存
        await self._clear_cache(session_id)
        
        self.logger.debug(
            f"记录历史事件: {session_id} - {event_type}"
        )
        
        return memory
    
    async def get_history_memories(
        self,
        session_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        use_cache: bool = True
    ) -> List[HistoryMemory]:
        """
        获取历史记忆
        
        Args:
            session_id: 会话ID
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
            use_cache: 是否使用缓存
            
        Returns:
            List[HistoryMemory]: 历史记忆列表
        """
        # 如果指定了时间范围，不使用缓存
        if start_time or end_time:
            use_cache = False
        
        cache_key = CacheKeyGenerator.history_memory_key(session_id)
        
        # 尝试从缓存获取
        if use_cache and self.cache_manager:
            cached = await self.cache_manager.get(cache_key)
            if cached:
                return cached
        
        # 从数据库获取
        memories = await self.memory_repository.get_history_memories(
            session_id=session_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # 缓存结果（仅当没有时间限制时）
        if use_cache and self.cache_manager and memories:
            await self.cache_manager.set(
                cache_key,
                memories,
                ttl=self.cache_ttl
            )
        
        return memories
    
    async def get_timeline(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取时间线
        
        Args:
            session_id: 会话ID
            limit: 限制数量
            
        Returns:
            List[Dict]: 时间线事件列表
        """
        memories = await self.get_history_memories(session_id)
        
        # 按时间排序
        memories.sort(key=lambda m: m.timestamp, reverse=True)
        
        # 构建时间线
        timeline = []
        for memory in memories[:limit]:
            timeline.append({
                'timestamp': memory.timestamp.isoformat(),
                'event_type': memory.event_type,
                'summary': memory.summary,
                'importance': memory.importance,
                'participants': memory.participants,
                'location': memory.location
            })
        
        return timeline
    
    async def generate_summary(
        self,
        session_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> str:
        """
        生成历史摘要
        
        Args:
            session_id: 会话ID
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
            
        Returns:
            str: 历史摘要
        """
        memories = await self.get_history_memories(
            session_id,
            start_time,
            end_time
        )
        
        if not memories:
            return "暂无历史记录"
        
        # 按重要性排序
        important_memories = sorted(
            memories,
            key=lambda m: m.importance,
            reverse=True
        )[:20]
        
        # 使用LLM生成摘要
        if self.model_scheduler:
            return await self._generate_llm_summary(important_memories)
        else:
            return self._generate_simple_summary(important_memories)
    
    async def _generate_summary(self, memory: HistoryMemory) -> str:
        """
        生成单条记忆的摘要
        
        Args:
            memory: 历史记忆
            
        Returns:
            str: 摘要
        """
        # 简单截断
        if len(memory.content) <= 100:
            return memory.content
        return memory.content[:97] + "..."
    
    async def _generate_llm_summary(self, memories: List[HistoryMemory]) -> str:
        """
        使用LLM生成摘要
        
        Args:
            memories: 历史记忆列表
            
        Returns:
            str: 摘要
        """
        # 构建记忆摘要
        memory_summaries = []
        for i, memory in enumerate(memories[:10], 1):
            memory_summaries.append(
                f"{i}. [{memory.event_type}] {memory.summary}"
            )
        
        prompt = f"""请将以下游戏历史事件总结为简短的摘要（不超过200字）。

事件列表:
{chr(10).join(memory_summaries)}

请直接返回摘要文本，不要包含其他内容。
"""
        
        request_context = ProviderRequest(
            messages=[
                ChatMessage(
                    role='system',
                    content='你是摘要生成专家，请生成简洁准确的游戏历史摘要。'
                ),
                ChatMessage(role='user', content=prompt)
            ],
            max_tokens=300,
            temperature=0.3
        )
        
        try:
            response = await self.model_scheduler.chat(request_context)
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.warning(f"LLM摘要生成失败: {e}")
            return self._generate_simple_summary(memories)
    
    def _generate_simple_summary(self, memories: List[HistoryMemory]) -> str:
        """
        生成简单摘要
        
        Args:
            memories: 历史记忆列表
            
        Returns:
            str: 摘要
        """
        if not memories:
            return "暂无历史记录"
        
        important = [m for m in memories if m.importance >= 0.7]
        if important:
            summaries = [m.summary for m in important[:5]]
            return "、".join(summaries)
        else:
            return f"共{len(memories)}条记录，最近: {memories[0].summary}"
    
    async def _clear_cache(self, session_id: str) -> None:
        """清除缓存"""
        if not self.cache_manager:
            return
        
        cache_key = CacheKeyGenerator.history_memory_key(session_id)
        await self.cache_manager.delete(cache_key)


# ==================== NPC记忆存储服务 ====================

class NPCMemoryStorageService:
    """NPC记忆存储服务"""
    
    def __init__(
        self,
        memory_repository: IMemoryRepository,
        cache_manager: Optional[ICacheManager] = None,
        cache_ttl: int = 300
    ):
        """
        初始化NPC记忆存储服务
        
        Args:
            memory_repository: 记忆仓库
            cache_manager: 缓存管理器（可选）
            cache_ttl: 缓存有效期（秒）
        """
        self.memory_repository = memory_repository
        self.cache_manager = cache_manager
        self.cache_ttl = cache_ttl
        self.logger = app_logger
    
    async def save_interaction(
        self,
        npc_id: str,
        session_id: str,
        task: DispatchedTask,
        response: NPCResponse,
        relationship_delta: float = 0.0,
        importance: float = 0.5
    ) -> NPCMemoryRecord:
        """
        保存NPC交互记录
        
        Args:
            npc_id: NPC ID
            session_id: 会话ID
            task: 分发的任务
            response: NPC响应
            relationship_delta: 关系变化值
            importance: 重要性 0-1
            
        Returns:
            NPCMemoryRecord: 创建的记忆记录
        """
        character_id = task.original_input.original_input.character_id
        
        record = NPCMemoryRecord(
            record_id=str(uuid.uuid4()),
            npc_id=npc_id,
            session_id=session_id,
            timestamp=datetime.now(),
            interaction=task.original_input.original_input.content,
            response=response.response,
            emotion=response.emotion,
            attitude=response.attitude,
            character_id=character_id,
            summary="",  # 将异步生成
            importance=min(max(importance, 0.0), 1.0),
            relationship_delta=relationship_delta,
            compressed=False,
            metadata={
                'action': response.action,
                'task_type': task.input_type.value
            }
        )
        
        # 生成摘要
        record.summary = self._generate_simple_summary(record)
        
        # 保存到数据库
        await self.memory_repository.save_npc_memory(record)
        
        # 清除缓存
        await self._clear_cache(npc_id, session_id)
        
        self.logger.debug(
            f"保存NPC交互记录: {npc_id} - {len(record.interaction)}字"
        )
        
        return record
    
    async def get_npc_memories(
        self,
        npc_id: str,
        session_id: Optional[str] = None,
        use_cache: bool = True
    ) -> List[NPCMemoryRecord]:
        """
        获取NPC记忆
        
        Args:
            npc_id: NPC ID
            session_id: 会话ID（可选）
            use_cache: 是否使用缓存
            
        Returns:
            List[NPCMemoryRecord]: NPC记忆列表
        """
        cache_key = CacheKeyGenerator.npc_memory_key(npc_id, session_id)
        
        # 尝试从缓存获取
        if use_cache and self.cache_manager:
            cached = await self.cache_manager.get(cache_key)
            if cached:
                return cached
        
        # 从数据库获取
        memories = await self.memory_repository.get_npc_memories(
            npc_id=npc_id,
            session_id=session_id
        )
        
        # 缓存结果
        if use_cache and self.cache_manager and memories:
            await self.cache_manager.set(
                cache_key,
                memories,
                ttl=self.cache_ttl
            )
        
        return memories
    
    async def compress_memories(
        self,
        npc_id: str,
        session_id: str,
        target_count: int = 50
    ) -> int:
        """
        压缩NPC记忆数量
        
        Args:
            npc_id: NPC ID
            session_id: 会话ID
            target_count: 目标数量
            
        Returns:
            int: 压缩后的记忆数量
        """
        memories = await self.get_npc_memories(npc_id, session_id, use_cache=False)
        
        if len(memories) <= target_count:
            return len(memories)
        
        # 按重要性和时间排序
        scored_memories = []
        for i, memory in enumerate(memories):
            score = memory.importance * 0.7 + self._calculate_recency_score(memory.timestamp) * 0.3
            scored_memories.append((i, memory, score))
        
        # 保留重要的记忆
        scored_memories.sort(key=lambda x: x[2], reverse=True)
        selected_indices = set(item[0] for item in scored_memories[:target_count])
        
        # 标记需要压缩的记忆
        compressed_count = 0
        for i, memory in enumerate(memories):
            if i not in selected_indices and not memory.compressed:
                memory.compressed = True
                await self.memory_repository.save_npc_memory(memory)
                compressed_count += 1
        
        # 清除缓存
        await self._clear_cache(npc_id, session_id)
        
        self.logger.info(
            f"压缩NPC记忆: {npc_id} - {compressed_count}条已压缩"
        )
        
        return target_count
    
    def _calculate_recency_score(self, timestamp: datetime) -> float:
        """
        计算近期性分数
        
        Args:
            timestamp: 时间戳
            
        Returns:
            float: 近期性分数 0-1
        """
        now = datetime.now()
        time_diff = (now - timestamp).total_seconds()
        
        # 7天内的记忆给予较高分数
        if time_diff < 7 * 24 * 3600:  # 7天
            return 1.0 - (time_diff / (7 * 24 * 3600)) * 0.5
        else:
            # 超过7天的记忆分数递减
            max_age = 30 * 24 * 3600  # 30天
            return max(0.1, 0.5 - ((time_diff - 7 * 24 * 3600) / max_age) * 0.4)
    
    def _generate_simple_summary(self, record: NPCMemoryRecord) -> str:
        """
        生成简单摘要
        
        Args:
            record: NPC记忆记录
            
        Returns:
            str: 摘要
        """
        if len(record.interaction) <= 50:
            return record.interaction
        return record.interaction[:47] + "..."
    
    async def _clear_cache(self, npc_id: str, session_id: Optional[str] = None) -> None:
        """清除缓存"""
        if not self.cache_manager:
            return
        
        cache_key = CacheKeyGenerator.npc_memory_key(npc_id, session_id)
        await self.cache_manager.delete(cache_key)


# ==================== 记忆检索API ====================

class MemoryRetrievalService:
    """记忆检索服务"""
    
    def __init__(
        self,
        memory_repository: IMemoryRepository,
        model_scheduler: Optional[ProviderManager] = None,
        cache_manager: Optional[ICacheManager] = None,
        cache_ttl: int = 60
    ):
        """
        初始化记忆检索服务
        
        Args:
            memory_repository: 记忆仓库
            model_scheduler: 模型调度器（用于语义搜索）
            cache_manager: 缓存管理器（可选）
            cache_ttl: 缓存有效期（秒）
        """
        self.memory_repository = memory_repository
        self.model_scheduler = model_scheduler
        self.cache_manager = cache_manager
        self.cache_ttl = cache_ttl
        self.logger = app_logger
    
    async def search(
        self,
        query: MemorySearchQuery,
        use_cache: bool = True
    ) -> List[MemorySearchResult]:
        """
        搜索记忆
        
        Args:
            query: 搜索查询
            use_cache: 是否使用缓存
            
        Returns:
            List[MemorySearchResult]: 搜索结果列表
        """
        cache_key = CacheKeyGenerator.search_cache_key(query)
        
        # 尝试从缓存获取
        if use_cache and self.cache_manager:
            cached = await self.cache_manager.get(cache_key)
            if cached:
                return cached
        
        # 从数据库搜索
        results = await self.memory_repository.search_memories(query)
        
        # 缓存结果
        if use_cache and self.cache_manager:
            await self.cache_manager.set(
                cache_key,
                results,
                ttl=self.cache_ttl
            )
        
        return results
    
    async def semantic_search(
        self,
        session_id: str,
        query_text: str,
        memory_types: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[MemorySearchResult]:
        """
        语义搜索
        
        Args:
            session_id: 会话ID
            query_text: 查询文本
            memory_types: 记忆类型列表（可选）
            limit: 返回数量限制
            
        Returns:
            List[MemorySearchResult]: 搜索结果列表
        """
        search_query = MemorySearchQuery(
            session_id=session_id,
            query_text=query_text,
            memory_types=memory_types,
            limit=limit
        )
        
        # 如果有模型调度器，使用语义搜索
        if self.model_scheduler:
            return await self._llm_semantic_search(search_query)
        else:
            return await self.search(search_query)
    
    async def _llm_semantic_search(
        self,
        query: MemorySearchQuery
    ) -> List[MemorySearchResult]:
        """
        使用LLM进行语义搜索
        
        Args:
            query: 搜索查询
            
        Returns:
            List[MemorySearchResult]: 搜索结果列表
        """
        # 先获取候选记忆
        base_results = await self.search(query)
        
        if not base_results:
            return []
        
        # 如果结果已经足够少，直接返回
        if len(base_results) <= query.limit:
            return base_results
        
        # 使用LLM重新评分
        try:
            memory_summaries = []
            for i, result in enumerate(base_results):
                memory_summaries.append(
                    f"{i+1}. [{result.memory_type}] {result.content[:100]}"
                )
            
            prompt = f"""请评估以下查询与记忆的相关性，并返回最相关的记忆编号。

查询: {query.query_text}

记忆列表:
{chr(10).join(memory_summaries)}

请以JSON格式返回：
- selected_indices: 相关记忆的编号列表（按相关性排序）
- scores: 每个记忆的相关性分数（0.0-1.0）

示例:
{{
    "selected_indices": [1, 3, 5],
    "scores": [0.9, 0.7, 0.5]
}}
"""
            
            request_context = ProviderRequest(
                messages=[
                    ChatMessage(
                        role='system',
                        content='你是语义搜索专家，请准确评估查询与记忆的相关性。'
                    ),
                    ChatMessage(role='user', content=prompt)
                ],
                max_tokens=500,
                temperature=0.2
            )
            
            response = await self.model_scheduler.chat(request_context)
            
            # 解析结果
            import json
            result = json.loads(response.choices[0].message.content)
            selected_indices = result.get('selected_indices', [])
            scores = result.get('scores', [])
            
            # 构建结果
            final_results = []
            for idx, score in zip(selected_indices, scores):
                if idx - 1 < len(base_results):
                    base_results[idx - 1].relevance_score = score
                    final_results.append(base_results[idx - 1])
            
            return final_results[:query.limit]
            
        except Exception as e:
            self.logger.warning(f"LLM语义搜索失败: {e}")
            return base_results[:query.limit]
    
    async def get_relevant_memories_for_npc(
        self,
        npc_id: str,
        session_id: str,
        query_text: str,
        character_id: Optional[str] = None,
        limit: int = 5
    ) -> List[MemorySearchResult]:
        """
        获取NPC相关的记忆
        
        Args:
            npc_id: NPC ID
            session_id: 会话ID
            query_text: 查询文本
            character_id: 角色ID（可选，优先返回与该角色相关的记忆）
            limit: 返回数量限制
            
        Returns:
            List[MemorySearchResult]: 搜索结果列表
        """
        search_query = MemorySearchQuery(
            session_id=session_id,
            query_text=query_text,
            memory_types=['npc'],
            npc_ids=[npc_id],
            limit=limit * 2  # 获取更多候选
        )
        
        results = await self.search(search_query)
        
        # 如果指定了角色ID，优先返回与该角色相关的记忆
        if character_id:
            relevant = []
            other = []
            for result in results:
                char_id = result.metadata.get('character_id')
                if char_id == character_id:
                    relevant.append(result)
                else:
                    other.append(result)
            results = relevant[:limit] + other[:limit - len(relevant)]
        
        return results[:limit]
    
    async def get_relevant_memories_for_scene(
        self,
        session_id: str,
        scene_id: str,
        query_text: Optional[str] = None,
        limit: int = 5
    ) -> List[MemorySearchResult]:
        """
        获取场景相关的记忆
        
        Args:
            session_id: 会话ID
            scene_id: 场景ID
            query_text: 查询文本（可选）
            limit: 返回数量限制
            
        Returns:
            List[MemorySearchResult]: 搜索结果列表
        """
        search_query = MemorySearchQuery(
            session_id=session_id,
            query_text=query_text or f"场景 {scene_id} 的事件",
            memory_types=['scene', 'history'],
            scene_ids=[scene_id],
            limit=limit
        )
        
        return await self.search(search_query)


# ==================== 记忆管理器工厂 ====================

class MemoryManagerFactory:
    """记忆管理器工厂"""
    
    @staticmethod
    def create_scene_memory_manager(
        memory_repository: IMemoryRepository,
        cache_manager: Optional[ICacheManager] = None,
        cache_ttl: int = 300
    ) -> SceneMemoryManager:
        """
        创建场景记忆管理器
        
        Args:
            memory_repository: 记忆仓库
            cache_manager: 缓存管理器（可选）
            cache_ttl: 缓存有效期（秒）
            
        Returns:
            SceneMemoryManager: 场景记忆管理器
        """
        return SceneMemoryManager(
            memory_repository=memory_repository,
            cache_manager=cache_manager,
            cache_ttl=cache_ttl
        )
    
    @staticmethod
    def create_history_memory_manager(
        memory_repository: IMemoryRepository,
        model_scheduler: Optional[ProviderManager] = None,
        cache_manager: Optional[ICacheManager] = None,
        cache_ttl: int = 300
    ) -> HistoryMemoryManager:
        """
        创建历史记忆管理器
        
        Args:
            memory_repository: 记忆仓库
            model_scheduler: 模型调度器（可选）
            cache_manager: 缓存管理器（可选）
            cache_ttl: 缓存有效期（秒）
            
        Returns:
            HistoryMemoryManager: 历史记忆管理器
        """
        return HistoryMemoryManager(
            memory_repository=memory_repository,
            model_scheduler=model_scheduler,
            cache_manager=cache_manager,
            cache_ttl=cache_ttl
        )
    
    @staticmethod
    def create_npc_memory_storage_service(
        memory_repository: IMemoryRepository,
        cache_manager: Optional[ICacheManager] = None,
        cache_ttl: int = 300
    ) -> NPCMemoryStorageService:
        """
        创建NPC记忆存储服务
        
        Args:
            memory_repository: 记忆仓库
            cache_manager: 缓存管理器（可选）
            cache_ttl: 缓存有效期（秒）
            
        Returns:
            NPCMemoryStorageService: NPC记忆存储服务
        """
        return NPCMemoryStorageService(
            memory_repository=memory_repository,
            cache_manager=cache_manager,
            cache_ttl=cache_ttl
        )
    
    @staticmethod
    def create_memory_retrieval_service(
        memory_repository: IMemoryRepository,
        model_scheduler: Optional[ProviderManager] = None,
        cache_manager: Optional[ICacheManager] = None,
        cache_ttl: int = 60
    ) -> MemoryRetrievalService:
        """
        创建记忆检索服务
        
        Args:
            memory_repository: 记忆仓库
            model_scheduler: 模型调度器（可选）
            cache_manager: 缓存管理器（可选）
            cache_ttl: 缓存有效期（秒）
            
        Returns:
            MemoryRetrievalService: 记忆检索服务
        """
        return MemoryRetrievalService(
            memory_repository=memory_repository,
            model_scheduler=model_scheduler,
            cache_manager=cache_manager,
            cache_ttl=cache_ttl
        )