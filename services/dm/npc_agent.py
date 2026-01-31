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
    ClassifiedInput,
    InputType
)
from ...data_storage.interfaces import Entity
from ...agent.core import BaseAgent
from ...provider import ProviderManager, ProviderRequest, ChatMessage
from ...core.logging import app_logger

# 导入增强的记忆系统和情绪系统
from .npc_memory_system import EnhancedNPCMemory
from .npc_emotion_system import (
    EmotionStateMachine,
    BehaviorDecisionTree,
    RelationshipManager,
    EmotionType
)


class NPCAgent(BaseAgent):
    """NPC智能体"""
    
    def __init__(
        self,
        agent_id: str,
        npc_id: str,
        npc_data: Entity,
        model_scheduler: ProviderManager,
        npc_memory: Optional[EnhancedNPCMemory] = None,
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
        
        # 记忆系统
        self.memory = npc_memory or EnhancedNPCMemory(
            npc_id=npc_id,
            model_scheduler=model_scheduler
        )
        
        # 情绪状态机
        self.emotion_state_machine = EmotionStateMachine(
            personality=self.personality
        )
        
        # 行为决策树
        self.behavior_decision_tree = BehaviorDecisionTree(
            personality=self.personality,
            model_scheduler=model_scheduler
        )
        
        # 关系管理器
        self.relationship_manager = RelationshipManager(
            personality=self.personality
        )
        
        # 系统提示
        self.system_prompt = self._build_npc_prompt()
        
        # 多轮对话上下文
        self.conversation_context: List[Dict[str, str]] = []
        self.max_context_length = 10
        
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
            input_data = task.original_input.original_input
            character_id = input_data.character_id
            input_type = task.input_type
            
            # 获取相关记忆
            relevant_memories = await self.memory.retrieve_relevant(task)
            
            # 获取与角色的关系值
            relationship_value = await self.memory.get_relationship(character_id)
            
            # 更新情绪状态
            input_emotion_type = self._classify_input_emotion(task)
            emotional_state = await self.emotion_state_machine.update_emotion(
                input_type=input_emotion_type,
                intensity=self._estimate_input_intensity(task)
            )
            
            # 决定行为
            behavior_decision = await self.behavior_decision_tree.decide_action(
                emotional_state=emotional_state,
                task=task,
                relationship_value=relationship_value
            )
            
            # 构建交互上下文
            context = self._build_interaction_context(
                task,
                relevant_memories,
                relationship_value,
                emotional_state,
                behavior_decision
            )
            
            # 生成响应
            response = await self._generate_response(context, emotional_state)
            
            # 更新记忆
            await self.memory.add_interaction(task, response)
            
            # 更新关系值
            await self.relationship_manager.update_relationship(
                character_id=character_id,
                interaction_type=self._get_interaction_type(input_type),
                attitude=response.attitude,
                emotion=response.emotion,
                context={'task_type': input_type.value}
            )
            
            # 同步关系值到记忆系统
            new_relationship = self.relationship_manager.get_relationship(character_id)
            await self.memory.set_relationship(character_id, new_relationship)
            
            # 更新对话上下文
            self._update_conversation_context(input_data, response)
            
            self.logger.info(
                f"NPC {self.npc_data.properties.get('name')} 响应: "
                f"{response.response[:50]}... | 情绪: {emotional_state.primary_emotion.value}"
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
        relationship_value: float,
        emotional_state,
        behavior_decision
    ) -> str:
        """
        构建交互上下文
        
        Args:
            task: 分发的任务
            memories: 相关记忆
            relationship_value: 关系值
            emotional_state: 情绪状态
            behavior_decision: 行为决策
            
        Returns:
            str: 交互上下文
        """
        context_parts = []
        
        # 添加当前交互
        input_data = task.original_input.original_input
        context_parts.append(f"玩家{input_data.character_name}说: {input_data.content}")
        
        # 添加关系状态
        relationship_status = self.relationship_manager.get_relationship_status(
            input_data.character_id
        )
        context_parts.append(f"\n当前关系值: {relationship_value:.1f}/10 ({relationship_status})")
        
        # 添加情绪状态
        context_parts.append(
            f"当前情绪: {emotional_state.primary_emotion.value} "
            f"(强度: {emotional_state.emotion_intensity:.2f}, "
            f"心情: {emotional_state.mood:.2f})"
        )
        
        # 添加行为决策
        context_parts.append(f"行为倾向: {behavior_decision.action}")
        
        # 添加对话历史上下文
        if self.conversation_context:
            context_parts.append("\n最近的对话:")
            recent_context = self.conversation_context[-3:]  # 最近3轮
            for ctx in recent_context:
                context_parts.append(f"- 玩家: {ctx['player']}")
                context_parts.append(f"  NPC: {ctx['npc'][:50]}...")
        
        # 添加相关记忆
        if memories:
            context_parts.append("\n相关记忆:")
            for i, memory in enumerate(memories, 1):
                context_parts.append(f"{i}. {memory.summary}")
        
        return "\n".join(context_parts)
    
    def _classify_input_emotion(self, task: DispatchedTask) -> str:
        """
        分类输入情绪类型
        
        Args:
            task: 分发的任务
            
        Returns:
            str: 情绪类型 ('positive', 'negative', 'threat', 'neutral')
        """
        content = task.original_input.original_input.content.lower()
        
        # 简单关键词分类
        positive_keywords = ['谢谢', '感谢', '帮助', '友好', '喜欢', '赞美', '谢谢', 'help', 'thank', 'love', 'like']
        negative_keywords = ['讨厌', '恨', '伤害', '攻击', '愤怒', '讨厌', 'hate', 'hurt', 'attack', 'angry']
        threat_keywords = ['威胁', '杀', '死亡', '威胁', 'kill', 'die', 'death', 'threat', 'murder']
        
        if any(kw in content for kw in positive_keywords):
            return 'positive'
        elif any(kw in content for kw in threat_keywords):
            return 'threat'
        elif any(kw in content for kw in negative_keywords):
            return 'negative'
        else:
            return 'neutral'
    
    def _estimate_input_intensity(self, task: DispatchedTask) -> float:
        """
        估算输入强度
        
        Args:
            task: 分发的任务
            
        Returns:
            float: 强度 0.0-1.0
        """
        content = task.original_input.original_input.content
        
        # 基于内容长度和感叹号数量
        intensity = min(len(content) / 100, 1.0)
        exclamation_count = content.count('!')
        intensity += exclamation_count * 0.1
        
        return min(intensity, 1.0)
    
    def _get_interaction_type(self, input_type: InputType) -> str:
        """
        获取交互类型
        
        Args:
            input_type: 输入类型
            
        Returns:
            str: 交互类型
        """
        if input_type == InputType.DIALOGUE:
            return 'dialogue'
        elif input_type == InputType.ACTION:
            return 'action'
        else:
            return 'neutral'
    
    def _update_conversation_context(
        self,
        input_data,
        response: NPCResponse
    ) -> None:
        """
        更新对话上下文
        
        Args:
            input_data: 输入数据
            response: NPC响应
        """
        self.conversation_context.append({
            'player': input_data.content,
            'npc': response.response
        })
        
        # 限制上下文长度
        if len(self.conversation_context) > self.max_context_length:
            self.conversation_context.pop(0)
    
    async def decay_emotional_state(self, decay_rate: float = 0.1) -> None:
        """
        衰减情绪状态
        
        Args:
            decay_rate: 衰减率
        """
        self.emotion_state_machine.decay_emotion(decay_rate)
        self.relationship_manager.decay_relationships()
        self.logger.debug(f"NPC {self.npc_id} 情绪状态已衰减")
    
    async def _generate_response(
        self,
        context: str,
        emotional_state
    ) -> NPCResponse:
        """
        生成NPC响应
        
        Args:
            context: 交互上下文
            emotional_state: 当前情绪状态
            
        Returns:
            NPCResponse: NPC响应
        """
        # 根据情绪状态调整温度
        base_temperature = 0.8
        if emotional_state.emotion_intensity > 0.7:
            base_temperature += 0.2  # 高情绪强度增加随机性
        elif emotional_state.emotion_intensity < 0.3:
            base_temperature -= 0.2  # 低情绪强度增加稳定性
        
        prompt = f"""{self.system_prompt}

当前情境:
{context}

当前情绪状态说明：
- 主要情绪: {emotional_state.primary_emotion.value}
- 情绪强度: {emotional_state.emotion_intensity:.2f}
- 心情值: {emotional_state.mood:.2f} (负值表示负面，正值表示正面)
- 压力值: {emotional_state.stress_level:.2f}

请生成你的回应，务必体现当前的情绪状态和性格特征。

请以JSON格式返回，包含：
- response: 你的话语
- action: 你的行动（如有）
- emotion: 表达的情绪（joy/sadness/anger/fear/disgust/surprise/love/trust/neutral）
- attitude: 对玩家的态度（positive/negative/neutral）

情绪选择指南：
- joy/love/trust: 积极、快乐、喜爱的情绪
- sadness/anger/fear/disgust: 负面、痛苦、恐惧、厌恶的情绪
- surprise: 惊讶的情绪
- neutral: 中性情绪
"""
        
        request_context = ProviderRequest(
            messages=[
                ChatMessage(role='system', content=self.system_prompt),
                ChatMessage(role='user', content=prompt)
            ],
            max_tokens=800,
            temperature=base_temperature
        )
        
        response = await self.model_scheduler.chat(request_context)
        
        # 解析响应
        try:
            result = json.loads(response.choices[0].message.content)
            
            # 验证情绪类型
            emotion = result.get('emotion', 'neutral')
            valid_emotions = [e.value for e in EmotionType]
            if emotion not in valid_emotions:
                emotion = 'neutral'
            
            npc_response = NPCResponse(
                npc_id=self.npc_id,
                response=result.get('response', ''),
                action=result.get('action', ''),
                emotion=emotion,
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
        # 使用增强记忆系统的保存方法
        save_info = await self.memory.save_to_database()
        self.logger.info(
            f"保存NPC记忆: {save_info['npc_id']} - "
            f"{save_info['memory_count']}条记忆, "
            f"{save_info['relationship_count']}个关系"
        )
    
    async def load_memory_from_database(self) -> None:
        """从数据库加载NPC记忆"""
        # 使用增强记忆系统的加载方法
        await self.memory.load_from_database()
        self.logger.info(
            f"加载NPC记忆: {self.npc_id}"
        )
    
    def get_emotional_state(self):
        """
        获取当前情绪状态
        
        Returns:
            EmotionalState: 当前情绪状态
        """
        return self.emotion_state_machine.get_current_state()
    
    def get_relationships(self) -> Dict[str, float]:
        """
        获取所有关系值
        
        Returns:
            Dict[str, float]: 关系值字典
        """
        return self.relationship_manager.relationships.copy()
    
    async def get_npc_status(self) -> Dict[str, Any]:
        """
        获取NPC状态
        
        Returns:
            Dict: NPC状态信息
        """
        emotional_state = self.get_emotional_state()
        
        return {
            'npc_id': self.npc_id,
            'npc_name': self.npc_data.properties.get('name', 'Unknown'),
            'personality': self.personality.to_dict(),
            'emotional_state': emotional_state.to_dict(),
            'relationships': self.get_relationships(),
            'memory_count': self.memory.get_memory_count(),
            'conversation_turns': len(self.conversation_context)
        }
    
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
    model_scheduler: ProviderManager,
    npc_memory: Optional[EnhancedNPCMemory] = None
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
    
    # 加载记忆（如果未提供）
    if npc_memory is None:
        await agent.load_memory_from_database()
    
    return agent