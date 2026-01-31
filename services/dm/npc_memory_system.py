"""
NPC记忆系统
实现语义搜索记忆检索、记忆重要性评分、记忆摘要和压缩
"""

import logging
import hashlib
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from ...models.dm_models import (
    Memory,
    DispatchedTask,
    NPCResponse,
    ClassifiedInput,
    InputType
)
from ...provider import ProviderManager, ProviderRequest, ChatMessage
from ...core.logging import app_logger


@dataclass
class MemoryScore:
    """记忆评分"""
    memory_id: str
    relevance_score: float  # 相关性分数 0-1
    importance_score: float  # 重要性分数 0-1
    recency_score: float  # 近期性分数 0-1
    total_score: float  # 总分
    timestamp: datetime


class SemanticMemoryRetriever:
    """语义记忆检索器"""
    
    def __init__(
        self,
        model_scheduler: ProviderManager,
        temperature: float = 0.2
    ):
        """
        初始化语义记忆检索器
        
        Args:
            model_scheduler: 模型调度器
            temperature: 温度参数
        """
        self.model_scheduler = model_scheduler
        self.temperature = temperature
        self.logger = app_logger
    
    async def retrieve_relevant_memories(
        self,
        query: str,
        memories: List[Memory],
        limit: int = 5,
        character_id: Optional[str] = None
    ) -> List[Tuple[Memory, float]]:
        """
        语义检索相关记忆
        
        Args:
            query: 查询文本
            memories: 记忆列表
            limit: 返回数量限制
            character_id: 角色ID（可选，用于优先过滤）
            
        Returns:
            List[Tuple[Memory, float]]: (记忆, 相关性分数) 列表
        """
        if not memories:
            return []
        
        # 如果指定了角色ID，优先过滤该角色的记忆
        if character_id:
            character_memories = [
                m for m in memories
                if character_id in m.interaction
            ]
            if character_memories:
                memories = character_memories
        
        # 如果记忆数量少，直接返回最近的重要记忆
        if len(memories) <= limit:
            return [(m, self._calculate_simple_relevance(query, m)) 
                    for m in memories[-limit:]]
        
        # 使用LLM进行语义匹配
        try:
            return await self._semantic_search(query, memories, limit)
        except Exception as e:
            self.logger.warning(f"语义搜索失败，使用简单匹配: {e}")
            # 回退到简单匹配
            scored_memories = [
                (m, self._calculate_simple_relevance(query, m))
                for m in memories
            ]
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            return scored_memories[:limit]
    
    async def _semantic_search(
        self,
        query: str,
        memories: List[Memory],
        limit: int
    ) -> List[Tuple[Memory, float]]:
        """
        使用LLM进行语义搜索
        
        Args:
            query: 查询文本
            memories: 记忆列表
            limit: 返回数量限制
            
        Returns:
            List[Tuple[Memory, float]]: (记忆, 相关性分数) 列表
        """
        # 构建记忆摘要列表
        memory_summaries = []
        for i, memory in enumerate(memories):
            summary = memory.summary or f"{memory.interaction[:50]}..."
            memory_summaries.append(f"{i+1}. {summary}")
        
        prompt = f"""请评估以下查询与记忆的相关性，并返回最相关的记忆编号。

查询: {query}

记忆列表:
{chr(10).join(memory_summaries)}

请以JSON格式返回，包含：
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
            temperature=self.temperature
        )
        
        response = await self.model_scheduler.chat(request_context)
        
        # 解析结果
        try:
            import json
            result = json.loads(response.choices[0].message.content)
            selected_indices = result.get('selected_indices', [])
            scores = result.get('scores', [])
            
            # 构建结果
            scored_memories = []
            for idx, score in zip(selected_indices, scores):
                if idx - 1 < len(memories):
                    scored_memories.append((memories[idx - 1], score))
            
            return scored_memories[:limit]
            
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            self.logger.warning(f"解析语义搜索结果失败: {e}")
            # 回退到简单匹配
            return []
    
    def _calculate_simple_relevance(
        self,
        query: str,
        memory: Memory
    ) -> float:
        """
        计算简单相关性分数
        
        Args:
            query: 查询文本
            memory: 记忆
            
        Returns:
            float: 相关性分数 0-1
        """
        query_lower = query.lower()
        interaction_lower = memory.interaction.lower()
        response_lower = memory.response.lower()
        
        # 计算词汇重叠
        query_words = set(query_lower.split())
        interaction_words = set(interaction_lower.split())
        response_words = set(response_lower.split())
        
        overlap_interaction = len(query_words & interaction_words)
        overlap_response = len(query_words & response_words)
        
        max_overlap = max(len(query_words), 1)
        relevance = (overlap_interaction + overlap_response) / (2 * max_overlap)
        
        return min(relevance, 1.0)


class MemoryImportanceScorer:
    """记忆重要性评分器"""
    
    def __init__(
        self,
        model_scheduler: ProviderManager,
        temperature: float = 0.2
    ):
        """
        初始化记忆重要性评分器
        
        Args:
            model_scheduler: 模型调度器
            temperature: 温度参数
        """
        self.model_scheduler = model_scheduler
        self.temperature = temperature
        self.logger = app_logger
    
    async def score_memory(
        self,
        memory: Memory,
        context: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        评估记忆重要性
        
        Args:
            memory: 记忆
            context: 上下文信息（可选）
            
        Returns:
            float: 重要性分数 0-1
        """
        # 基础评分规则
        base_score = 0.5
        
        # 情绪影响：强烈情绪的记忆更重要
        if memory.emotion in ['joy', 'anger', 'fear', 'surprise']:
            base_score += 0.2
        elif memory.emotion in ['sadness', 'disgust']:
            base_score += 0.1
        
        # 交互长度：较长的交互可能包含更多信息
        if len(memory.interaction) > 100:
            base_score += 0.1
        if len(memory.response) > 100:
            base_score += 0.1
        
        # 使用LLM进行更精确的评分
        try:
            llm_score = await self._llm_score(memory, context)
            return (base_score + llm_score) / 2
        except Exception as e:
            self.logger.warning(f"LLM评分失败，使用基础评分: {e}")
            return min(base_score, 1.0)
    
    async def _llm_score(
        self,
        memory: Memory,
        context: Optional[Dict[str, Any]]
    ) -> float:
        """
        使用LLM评估重要性
        
        Args:
            memory: 记忆
            context: 上下文信息
            
        Returns:
            float: 重要性分数 0-1
        """
        context_str = ""
        if context:
            context_str = f"\n上下文: {context}"
        
        prompt = f"""请评估以下NPC记忆的重要性。

记忆内容:
交互: {memory.interaction}
回应: {memory.response}
情绪: {memory.emotion}
摘要: {memory.summary}{context_str}

请以JSON格式返回：
- importance: 重要性分数（0.0-1.0）
- reason: 评估原因

评估标准：
1. 包含重要信息（如角色关系、剧情关键点）的记忆更重要
2. 强烈情绪体验的记忆更重要
3. 影响角色决策的记忆更重要
4. 有持续影响的事件记忆更重要
"""
        
        request_context = ProviderRequest(
            messages=[
                ChatMessage(
                    role='system',
                    content='你是记忆评估专家，请准确评估记忆的重要性。'
                ),
                ChatMessage(role='user', content=prompt)
            ],
            max_tokens=300,
            temperature=self.temperature
        )
        
        response = await self.model_scheduler.chat(request_context)
        
        try:
            import json
            result = json.loads(response.choices[0].message.content)
            return max(0.0, min(1.0, result.get('importance', 0.5)))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"解析LLM评分失败: {e}")
            return 0.5


class MemorySummarizer:
    """记忆摘要生成器"""
    
    def __init__(
        self,
        model_scheduler: ProviderManager,
        temperature: float = 0.3,
        max_summary_length: int = 100
    ):
        """
        初始化记忆摘要生成器
        
        Args:
            model_scheduler: 模型调度器
            temperature: 温度参数
            max_summary_length: 最大摘要长度
        """
        self.model_scheduler = model_scheduler
        self.temperature = temperature
        self.max_summary_length = max_summary_length
        self.logger = app_logger
    
    async def generate_summary(
        self,
        memory: Memory
    ) -> str:
        """
        生成记忆摘要
        
        Args:
            memory: 记忆
            
        Returns:
            str: 摘要
        """
        # 如果已有摘要且长度合适，直接返回
        if memory.summary and len(memory.summary) <= self.max_summary_length:
            return memory.summary
        
        # 尝试使用LLM生成摘要
        try:
            return await self._llm_summarize(memory)
        except Exception as e:
            self.logger.warning(f"LLM摘要生成失败，使用简单截断: {e}")
            return self._simple_truncate(memory)
    
    async def _llm_summarize(self, memory: Memory) -> str:
        """
        使用LLM生成摘要
        
        Args:
            memory: 记忆
            
        Returns:
            str: 摘要
        """
        prompt = f"""请将以下NPC交互记录压缩成简短摘要（不超过{self.max_summary_length}字）。

交互内容: {memory.interaction}
NPC回应: {memory.response}
情绪: {memory.emotion}

请直接返回摘要文本，不要包含其他内容。
"""
        
        request_context = ProviderRequest(
            messages=[
                ChatMessage(
                    role='system',
                    content='你是摘要生成专家，请生成简洁准确的摘要。'
                ),
                ChatMessage(role='user', content=prompt)
            ],
            max_tokens=150,
            temperature=self.temperature
        )
        
        response = await self.model_scheduler.chat(request_context)
        summary = response.choices[0].message.content.strip()
        
        # 确保不超过最大长度
        if len(summary) > self.max_summary_length:
            summary = summary[:self.max_summary_length]
        
        return summary
    
    def _simple_truncate(self, memory: Memory) -> str:
        """
        简单截断生成摘要
        
        Args:
            memory: 记忆
            
        Returns:
            str: 摘要
        """
        # 优先使用交互内容
        if len(memory.interaction) <= self.max_summary_length:
            return memory.interaction
        
        # 截断交互内容
        return memory.interaction[:self.max_summary_length - 3] + "..."
    
    async def compress_memories(
        self,
        memories: List[Memory],
        target_count: int
    ) -> List[Memory]:
        """
        压缩记忆数量
        
        Args:
            memories: 记忆列表
            target_count: 目标数量
            
        Returns:
            List[Memory]: 压缩后的记忆列表
        """
        if len(memories) <= target_count:
            return memories
        
        # 计算每条记忆的综合评分
        scored_memories = []
        for i, memory in enumerate(memories):
            recency_score = self._calculate_recency_score(memory.timestamp)
            total_score = recency_score  # 这里可以加入重要性评分
            scored_memories.append((i, memory, total_score))
        
        # 按分数排序并保留前N条
        scored_memories.sort(key=lambda x: x[2], reverse=True)
        selected_memories = [item[1] for item in scored_memories[:target_count]]
        
        # 按时间重新排序
        selected_memories.sort(key=lambda m: m.timestamp)
        
        self.logger.info(
            f"记忆压缩: {len(memories)} -> {len(selected_memories)}"
        )
        
        return selected_memories
    
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


class EnhancedNPCMemory:
    """增强的NPC记忆管理"""
    
    def __init__(
        self,
        npc_id: str,
        model_scheduler: ProviderManager,
        max_memories: int = 100,
        important_memory_threshold: float = 0.7
    ):
        """
        初始化增强的NPC记忆
        
        Args:
            npc_id: NPC ID
            model_scheduler: 模型调度器
            max_memories: 最大记忆数量
            important_memory_threshold: 重要记忆阈值
        """
        self.npc_id = npc_id
        self.memories: List[Memory] = []
        self.relationships: Dict[str, float] = {}  # character_id -> relationship_score
        self.max_memories = max_memories
        self.important_memory_threshold = important_memory_threshold
        
        # 初始化组件
        self.retriever = SemanticMemoryRetriever(model_scheduler)
        self.scorer = MemoryImportanceScorer(model_scheduler)
        self.summarizer = MemorySummarizer(model_scheduler)
        
        self.logger = app_logger
    
    async def add_interaction(
        self,
        task: DispatchedTask,
        response: NPCResponse
    ) -> None:
        """
        添加交互记忆
        
        Args:
            task: 分发的任务
            response: NPC响应
        """
        # 创建基础记忆对象
        memory = Memory(
            timestamp=task.original_input.original_input.timestamp,
            interaction=task.original_input.original_input.content,
            response=response.response,
            emotion=response.emotion,
            summary=""  # 将在下面生成
        )
        
        # 生成摘要
        memory.summary = await self.summarizer.generate_summary(memory)
        
        # 添加到记忆列表
        self.memories.append(memory)
        
        # 评估重要性
        importance = await self.scorer.score_memory(memory)
        self.logger.debug(f"记忆重要性: {importance:.2f}")
        
        # 限制记忆数量
        if len(self.memories) > self.max_memories:
            # 保留重要记忆
            important_memories = [
                m for m in self.memories
                if await self.scorer.score_memory(m) >= self.important_memory_threshold
            ]
            
            # 压缩非重要记忆
            normal_memories = [
                m for m in self.memories
                if await self.scorer.score_memory(m) < self.important_memory_threshold
            ]
            
            if len(important_memories) + len(normal_memories) > self.max_memories:
                # 保留重要的，压缩其他的
                keep_count = self.max_memories - len(important_memories)
                normal_memories = await self.summarizer.compress_memories(
                    normal_memories,
                    keep_count
                )
            
            # 重新组合
            self.memories = important_memories + normal_memories
            self.memories.sort(key=lambda m: m.timestamp)
        
        # 更新关系
        character_id = task.original_input.original_input.character_id
        await self._update_relationship(character_id, response)
        
        self.logger.debug(
            f"添加NPC记忆: {self.npc_id} - {len(self.memories)}条记忆"
        )
    
    async def retrieve_relevant(
        self,
        task: DispatchedTask,
        limit: int = 5
    ) -> List[Memory]:
        """
        检索相关记忆
        
        Args:
            task: 分发的任务
            limit: 返回的最大数量
            
        Returns:
            List[Memory]: 相关记忆列表
        """
        character_id = task.original_input.original_input.character_id
        query = task.original_input.original_input.content
        
        # 使用语义检索
        relevant_memories = await self.retriever.retrieve_relevant_memories(
            query=query,
            memories=self.memories,
            limit=limit,
            character_id=character_id
        )
        
        # 返回记忆对象列表
        return [memory for memory, _ in relevant_memories]
    
    async def get_relationship(self, character_id: str) -> float:
        """
        获取与角色的关系值
        
        Args:
            character_id: 角色ID
            
        Returns:
            float: 关系值 (0-10)
        """
        return self.relationships.get(character_id, 5.0)
    
    async def set_relationship(
        self,
        character_id: str,
        value: float
    ) -> None:
        """
        设置与角色的关系值
        
        Args:
            character_id: 角色ID
            value: 关系值 (0-10)
        """
        self.relationships[character_id] = max(0.0, min(10.0, value))
        self.logger.debug(
            f"设置关系值: {self.npc_id} -> {character_id} = {value:.1f}"
        )
    
    async def _update_relationship(
        self,
        character_id: str,
        response: NPCResponse
    ) -> None:
        """
        更新关系值
        
        Args:
            character_id: 角色ID
            response: NPC响应
        """
        # 基于态度更新关系值
        delta = 0.0
        if response.attitude == 'positive':
            delta = 0.5
        elif response.attitude == 'negative':
            delta = -0.5
        
        # 考虑情绪影响
        if response.emotion in ['joy', 'love', 'trust']:
            delta += 0.3
        elif response.emotion in ['anger', 'fear', 'disgust']:
            delta -= 0.3
        
        current = self.relationships.get(character_id, 5.0)
        new_value = max(0.0, min(10.0, current + delta))
        self.relationships[character_id] = new_value
        
        self.logger.debug(
            f"更新关系值: {self.npc_id} -> {character_id}: "
            f"{current:.1f} -> {new_value:.1f} (delta: {delta:+.1f})"
        )
    
    async def save_to_database(self) -> Dict[str, Any]:
        """
        保存记忆到数据库
        
        Returns:
            Dict: 保存的记录信息
        """
        # TODO: 实现数据库持久化
        self.logger.info(
            f"保存NPC记忆: {self.npc_id} - {len(self.memories)}条记忆"
        )
        return {
            'npc_id': self.npc_id,
            'memory_count': len(self.memories),
            'relationship_count': len(self.relationships)
        }
    
    async def load_from_database(self) -> None:
        """从数据库加载记忆"""
        # TODO: 实现数据库加载
        self.logger.info(
            f"加载NPC记忆: {self.npc_id}"
        )
    
    def get_memory_count(self) -> int:
        """
        获取记忆数量
        
        Returns:
            int: 记忆数量
        """
        return len(self.memories)
    
    def get_relationships(self) -> Dict[str, float]:
        """
        获取所有关系值
        
        Returns:
            Dict[str, float]: 关系值字典
        """
        return self.relationships.copy()