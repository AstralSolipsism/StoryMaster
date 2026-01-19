"""
NPC智能体
每个NPC作为独立的智能体实例，拥有独立记忆和性格
"""

import json
import logging
from typing import Dict, List, Optional, Any

from ...models.dm_models import (
    NPCPersonality,
    NPCResponse,
    Memory,
    DispatchedTask,
    ClassifiedInput
)
from ...models.dynamic_entity import Entity
from ...agent_orchestration.core import BaseAgent
from ...model_adapter import ModelScheduler, RequestContext, ChatMessage
from ...core.logging import app_logger


class NPCMemory:
    """NPC记忆管理"""
    
    def __init__(self, max_memories: int = 100):
        """
        初始化NPC记忆
        
        Args:
            max_memories: 最大记忆数量
        """
        self.memories: List[Memory] = []
        self.relationships: Dict[str, float] = {}  # character_id -> relationship_score
        self.max_memories = max_memories
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
        memory = Memory(
            timestamp=task.original_input.original_input.timestamp,
            interaction=task.original_input.original_input.content,
            response=response.response,
            emotion=response.emotion,
            summary=self._generate_summary(task, response)
        )
        
        self.memories.append(memory)
        
        # 限制记忆数量
        if len(self.memories) > self.max_memories:
            self.memories.pop(0)
        
        # 更新关系
        if response.attitude == 'positive':
            self._update_relationship(
                task.original_input.original_input.character_id,
                1.0
            )
        elif response.attitude == 'negative':
            self._update_relationship(
                task.original_input.original_input.character_id,
                -1.0
            )
        
        self.logger.debug(
            f"添加NPC记忆: {len(self.memories)}条记忆"
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
        
        # 简单实现：返回与该角色最近的交互
        relevant_memories = [
            memory for memory in self.memories[-20:]
            if character_id in memory.interaction or len(self.memories) <= limit
        ]
        
        # 限制返回数量
        return relevant_memories[-limit:]
    
    async def get_relationship(self, character_id: str) -> float:
        """
        获取与角色的关系值
        
        Args:
            character_id: 角色ID
            
        Returns:
            float: 关系值 (0-10)
        """
        return self.relationships.get(character_id, 5.0)
    
    async def set_relationship(self, character_id: str, value: float) -> None:
        """
        设置与角色的关系值
        
        Args:
            character_id: 角色ID
            value: 关系值 (0-10)
        """
        self.relationships[character_id] = max(0.0, min(10.0, value))
    
    def _update_relationship(self, character_id: str, delta: float) -> None:
        """
        更新关系值
        
        Args:
            character_id: 角色ID
            delta: 变化值
        """
        current = self.relationships.get(character_id, 5.0)
        new_value = max(0.0, min(10.0, current + delta))
        self.relationships[character_id] = new_value
    
    def _generate_summary(
        self,
        task: DispatchedTask,
        response: NPCResponse
    ) -> str:
        """
        生成交互摘要
        
        Args:
            task: 分发的任务
            response: NPC响应
            
        Returns:
            str: 摘要
        """
        content = task.original_input.original_input.content
        # 简单截断作为摘要
        if len(content) > 50:
            content = content[:50] + "..."
        return f"{content} -> {response.response[:50]}..."


class NPCAgent(BaseAgent):
    """NPC智能体"""
    
    def __init__(
        self,
        agent_id: str,
        npc_id: str,
        npc_data: Entity,
        model_scheduler: ModelScheduler,
        npc_memory: Optional[NPCMemory] = None,
        **kwargs
    ):
        """
        初始化NPC智能体
        
        Args:
            agent_id: 智能体ID
            npc_id: NPC ID
            npc_data: NPC数据实体
            model_scheduler: 模型调度器
            npc_memory: NPC记忆（可选）
        """
        super().__init__(
            agent_id=agent_id,
            model_scheduler=model_scheduler,
            **kwargs
        )
        self.npc_id = npc_id
        self.npc_data = npc_data
        self.model_scheduler = model_scheduler
        
        # NPC特性
        self.personality = self._load_personality(npc_data)
        self.relationships = {}
        
        # 记忆
        self.memory = npc_memory or NPCMemory()
        
        # 系统提示
        self.system_prompt = self._build_npc_prompt()
        
        self.logger = app_logger
    
    def _load_personality(self, npc_data: Entity) -> NPCPersonality:
        """
        加载NPC性格
        
        Args:
            npc_data: NPC数据实体
            
        Returns:
            NPCPersonality: NPC性格
        """
        properties = npc_data.properties
        return NPCPersonality(
            friendliness=properties.get('friendliness', 5.0),
            wisdom=properties.get('wisdom', 5.0),
            courage=properties.get('courage', 5.0),
            greed=properties.get('greed', 5.0),
            speech_style=properties.get('speech_style', '正常'),
            speech_pattern=properties.get('speech_pattern', '直接')
        )
    
    def _build_npc_prompt(self) -> str:
        """
        构建NPC系统提示
        
        Returns:
            str: 系统提示
        """
        name = self.npc_data.properties.get('name', 'Unknown')
        description = self.npc_data.properties.get('description', '')
        
        personality = self.personality
        
        return f"""你是{name}，一个D&D游戏中的NPC。

角色描述: {description}

性格特征:
- 友好度: {personality.friendliness}/10
- 智慧: {personality.wisdom}/10
- 勇气: {personality.courage}/10
- 贪婪: {personality.greed}/10

对话风格: {personality.speech_style}
说话方式: {personality.speech_pattern}

请根据你的性格和当前情境，自然地回应玩家的对话和行动。
保持角色性格的一致性，不要破坏角色设定。
在对话中体现你的性格特征。

重要规则：
1. 如果友好度>7，倾向于积极回应
2. 如果友好度<4，倾向于冷淡或警惕
3. 如果智慧>7，回答要更有深度
4. 如果勇气<4，面对威胁会退缩
5. 如果贪婪>7，对交易更感兴趣
"""
    
    async def process_interaction(
        self,
        task: DispatchedTask
    ) -> NPCResponse:
        """
        处理玩家交互
        
        Args:
            task: 分发的任务
            
        Returns:
            NPCResponse: NPC响应
        """
        try:
            # 获取相关记忆
            relevant_memories = await self.memory.retrieve_relevant(task)
            
            # 获取与角色的关系
            character_id = task.original_input.original_input.character_id
            relationship = await self.memory.get_relationship(character_id)
            
            # 构建交互上下文
            context = self._build_interaction_context(
                task,
                relevant_memories,
                relationship
            )
            
            # 生成响应
            response = await self._generate_response(context)
            
            # 更新记忆
            await self.memory.add_interaction(task, response)
            
            self.logger.info(
                f"NPC {self.npc_data.properties.get('name')} 响应: "
                f"{response.response[:50]}..."
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"NPC交互处理失败: {e}", exc_info=True)
            # 返回默认响应
            return NPCResponse(
                npc_id=self.npc_id,
                response="...",
                action="",
                emotion="neutral",
                attitude="neutral"
            )
    
    def _build_interaction_context(
        self,
        task: DispatchedTask,
        memories: List[Memory],
        relationship: float
    ) -> str:
        """
        构建交互上下文
        
        Args:
            task: 分发的任务
            memories: 相关记忆
            relationship: 关系值
            
        Returns:
            str: 交互上下文
        """
        context_parts = []
        
        # 添加当前交互
        input_data = task.original_input.original_input
        context_parts.append(f"玩家{input_data.character_name}说: {input_data.content}")
        
        # 添加关系状态
        context_parts.append(f"\n当前关系值: {relationship}/10")
        if relationship > 7:
            context_parts.append("关系状态: 友好")
        elif relationship < 4:
            context_parts.append("关系状态: 冷淡")
        else:
            context_parts.append("关系状态: 中立")
        
        # 添加相关记忆
        if memories:
            context_parts.append("\n相关记忆:")
            for memory in memories:
                context_parts.append(f"- {memory.summary}")
        
        return "\n".join(context_parts)
    
    async def _generate_response(self, context: str) -> NPCResponse:
        """
        生成NPC响应
        
        Args:
            context: 交互上下文
            
        Returns:
            NPCResponse: NPC响应
        """
        prompt = f"""{self.system_prompt}

当前情境:
{context}

请生成你的回应。

请以JSON格式返回，包含：
- response: 你的话语
- action: 你的行动（如有）
- emotion: 表达的情绪
- attitude: 对玩家的态度

情绪类型: positive, negative, neutral
态度类型: positive, negative, neutral
"""
        
        request_context = RequestContext(
            messages=[
                ChatMessage(role='system', content=self.system_prompt),
                ChatMessage(role='user', content=prompt)
            ],
            max_tokens=800,
            temperature=0.8
        )
        
        response = await self.model_scheduler.chat(request_context)
        
        # 解析响应
        try:
            result = json.loads(response.choices[0].message.content)
            
            npc_response = NPCResponse(
                npc_id=self.npc_id,
                response=result.get('response', ''),
                action=result.get('action', ''),
                emotion=result.get('emotion', 'neutral'),
                attitude=result.get('attitude', 'neutral')
            )
            
            return npc_response
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"NPC响应JSON解析失败: {e}")
            # 返回简单响应
            return NPCResponse(
                npc_id=self.npc_id,
                response="...",
                action="",
                emotion="neutral",
                attitude="neutral"
            )
    
    async def update_memory(
        self,
        inputs: List[Any],
        tasks: List[DispatchedTask],
        response: NPCResponse
    ) -> None:
        """
        更新NPC记忆
        
        Args:
            inputs: 玩家输入列表
            tasks: 分发的任务列表
            response: NPC响应
        """
        for task in tasks:
            if task.target_npc_id == self.npc_id:
                await self.memory.add_interaction(task, response)
    
    async def save_memory_to_database(self) -> None:
        """保存NPC记忆到数据库"""
        # TODO: 实现记忆持久化
        self.logger.info(
            f"保存NPC记忆: {self.npc_id} - {len(self.memory.memories)}条记忆"
        )
    
    async def load_memory_from_database(self) -> None:
        """从数据库加载NPC记忆"""
        # TODO: 实现记忆加载
        self.logger.info(
            f"加载NPC记忆: {self.npc_id}"
        )
    
    async def update_personality(
        self,
        personality: NPCPersonality
    ) -> None:
        """
        更新NPC性格
        
        Args:
            personality: 新的NPC性格
        """
        self.personality = personality
        self.system_prompt = self._build_npc_prompt()
        self.logger.info(f"更新NPC性格: {self.npc_id}")


# ==================== 工厂函数 ====================

async def create_npc_agent(
    npc_id: str,
    npc_data: Entity,
    model_scheduler: ModelScheduler,
    npc_memory: Optional[NPCMemory] = None
) -> NPCAgent:
    """
    创建NPC智能体实例
    
    Args:
        npc_id: NPC ID
        npc_data: NPC数据实体
        model_scheduler: 模型调度器
        npc_memory: NPC记忆（可选）
        
    Returns:
        NPCAgent: NPC智能体实例
    """
    agent_id = f"npc_{npc_id}"
    
    agent = NPCAgent(
        agent_id=agent_id,
        npc_id=npc_id,
        npc_data=npc_data,
        model_scheduler=model_scheduler,
        npc_memory=npc_memory
    )
    
    # 初始化智能体
    await agent.initialize()
    
    # 加载记忆（如果提供了）
    if npc_memory is None:
        await agent.load_memory_from_database()
    
    return agent