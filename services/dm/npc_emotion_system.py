"""
NPC情绪和行为反应系统
实现情绪状态机、行为决策树、个性特征影响
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from ...models.dm_models import (
    NPCPersonality,
    Memory,
    DispatchedTask,
    ClassifiedInput,
    InputType
)
from ...provider import ProviderManager, ProviderRequest, ChatMessage
from ...core.logging import app_logger


# ==================== 情绪枚举 ====================

class EmotionType(Enum):
    """情绪类型"""
    # 基础情绪
    JOY = "joy"           # 快乐
    SADNESS = "sadness"   # 悲伤
    ANGER = "anger"       # 愤怒
    FEAR = "fear"         # 恐惧
    DISGUST = "disgust"   # 厌恶
    SURPRISE = "surprise" # 惊讶
    
    # 复杂情绪
    LOVE = "love"         # 喜爱
    TRUST = "trust"       # 信任
    ANTICIPATION = "anticipation" # 期待
    NEUTRAL = "neutral"   # 中性


# ==================== 情绪状态 ====================

@dataclass
class EmotionalState:
    """情绪状态"""
    primary_emotion: EmotionType
    emotion_intensity: float  # 0.0-1.0
    mood: float  # -1.0 到 1.0 (负面到正面)
    stress_level: float  # 0.0-1.0
    last_updated: str = ""  # ISO格式时间戳
    
    def __post_init__(self):
        from datetime import datetime
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'primary_emotion': self.primary_emotion.value,
            'emotion_intensity': self.emotion_intensity,
            'mood': self.mood,
            'stress_level': self.stress_level,
            'last_updated': self.last_updated
        }


# ==================== 情绪状态机 ====================

class EmotionStateMachine:
    """情绪状态机"""
    
    # 情绪转移矩阵：当前情绪 -> 输入情绪 -> 新情绪概率
    TRANSITION_MATRIX = {
        EmotionType.NEUTRAL: {
            'positive': {EmotionType.JOY: 0.6, EmotionType.LOVE: 0.3, EmotionType.TRUST: 0.1},
            'negative': {EmotionType.ANGER: 0.4, EmotionType.FEAR: 0.3, EmotionType.SADNESS: 0.3},
            'threat': {EmotionType.FEAR: 0.7, EmotionType.ANGER: 0.3}
        },
        EmotionType.JOY: {
            'negative': {EmotionType.SADNESS: 0.4, EmotionType.ANGER: 0.3, EmotionType.SURPRISE: 0.3},
            'threat': {EmotionType.FEAR: 0.6, EmotionType.SURPRISE: 0.4}
        },
        EmotionType.ANGER: {
            'positive': {EmotionType.JOY: 0.3, EmotionType.NEUTRAL: 0.5, EmotionType.SURPRISE: 0.2},
            'threat': {EmotionType.ANGER: 0.5, EmotionType.FEAR: 0.3, EmotionType.DISGUST: 0.2}
        },
        EmotionType.FEAR: {
            'positive': {EmotionType.JOY: 0.2, EmotionType.TRUST: 0.4, EmotionType.NEUTRAL: 0.4},
            'negative': {EmotionType.SADNESS: 0.3, EmotionType.ANGER: 0.3, EmotionType.FEAR: 0.4}
        }
    }
    
    def __init__(
        self,
        personality: NPCPersonality,
        initial_state: Optional[EmotionalState] = None
    ):
        """
        初始化情绪状态机
        
        Args:
            personality: NPC性格
            initial_state: 初始情绪状态（可选）
        """
        self.personality = personality
        self.current_state = initial_state or EmotionalState(
            primary_emotion=EmotionType.NEUTRAL,
            emotion_intensity=0.5,
            mood=0.0,
            stress_level=0.0
        )
        self.logger = app_logger
    
    async def update_emotion(
        self,
        input_type: str,  # 'positive', 'negative', 'threat'
        intensity: float = 0.5
    ) -> EmotionalState:
        """
        更新情绪状态
        
        Args:
            input_type: 输入类型
            intensity: 强度 0.0-1.0
            
        Returns:
            EmotionalState: 更新后的情绪状态
        """
        # 根据性格调整情绪反应
        adjusted_intensity = self._adjust_by_personality(input_type, intensity)
        
        # 获取可能的情绪转移
        current_emotion = self.current_state.primary_emotion
        transitions = self.TRANSITION_MATRIX.get(
            current_emotion,
            self.TRANSITION_MATRIX[EmotionType.NEUTRAL]
        )
        possible_transitions = transitions.get(input_type, {})
        
        # 选择新情绪
        new_emotion = self._select_emotion(possible_transitions)
        
        # 更新情绪强度
        new_intensity = self._calculate_intensity(
            self.current_state.emotion_intensity,
            adjusted_intensity
        )
        
        # 更新心情和压力
        new_mood = self._update_mood(input_type, adjusted_intensity)
        new_stress = self._update_stress(input_type, adjusted_intensity)
        
        # 更新状态
        from datetime import datetime
        self.current_state = EmotionalState(
            primary_emotion=new_emotion,
            emotion_intensity=new_intensity,
            mood=new_mood,
            stress_level=new_stress,
            last_updated=datetime.now().isoformat()
        )
        
        self.logger.debug(
            f"情绪更新: {current_emotion.value} -> {new_emotion.value}, "
            f"强度: {new_intensity:.2f}, 心情: {new_mood:.2f}"
        )
        
        return self.current_state
    
    def _adjust_by_personality(
        self,
        input_type: str,
        intensity: float
    ) -> float:
        """
        根据性格调整强度
        
        Args:
            input_type: 输入类型
            intensity: 原始强度
            
        Returns:
            float: 调整后的强度
        """
        adjusted = intensity
        
        # 友好度影响正面情绪
        if input_type == 'positive':
            if self.personality.friendliness > 7:
                adjusted *= 1.2
            elif self.personality.friendliness < 4:
                adjusted *= 0.8
        
        # 勇气影响恐惧反应
        if input_type == 'threat':
            if self.personality.courage > 7:
                adjusted *= 0.7
            elif self.personality.courage < 4:
                adjusted *= 1.3
        
        # 贪婪影响积极反应
        if input_type == 'positive' and self.personality.greed > 7:
            adjusted *= 1.1
        
        return max(0.0, min(1.0, adjusted))
    
    def _select_emotion(
        self,
        transitions: Dict[EmotionType, float]
    ) -> EmotionType:
        """
        根据概率选择情绪
        
        Args:
            transitions: 情绪转移概率字典
            
        Returns:
            EmotionType: 选择的情绪
        """
        if not transitions:
            return EmotionType.NEUTRAL
        
        # 根据概率选择
        import random
        emotions = list(transitions.keys())
        probabilities = list(transitions.values())
        
        # 归一化概率
        total = sum(probabilities)
        if total == 0:
            return EmotionType.NEUTRAL
        
        normalized_probs = [p / total for p in probabilities]
        
        # 选择
        selected = random.choices(emotions, weights=normalized_probs, k=1)[0]
        return selected
    
    def _calculate_intensity(
        self,
        current_intensity: float,
        new_intensity: float
    ) -> float:
        """
        计算新的情绪强度
        
        Args:
            current_intensity: 当前强度
            new_intensity: 新输入强度
            
        Returns:
            float: 新强度
        """
        # 混合当前强度和新输入强度
        blended = current_intensity * 0.6 + new_intensity * 0.4
        return max(0.0, min(1.0, blended))
    
    def _update_mood(
        self,
        input_type: str,
        intensity: float
    ) -> float:
        """
        更新心情
        
        Args:
            input_type: 输入类型
            intensity: 强度
            
        Returns:
            float: 新心情值 (-1.0 到 1.0)
        """
        delta = 0.0
        
        if input_type == 'positive':
            delta = intensity * 0.3
        elif input_type == 'negative':
            delta = -intensity * 0.3
        elif input_type == 'threat':
            delta = -intensity * 0.2
        
        new_mood = self.current_state.mood + delta
        return max(-1.0, min(1.0, new_mood))
    
    def _update_stress(
        self,
        input_type: str,
        intensity: float
    ) -> float:
        """
        更新压力水平
        
        Args:
            input_type: 输入类型
            intensity: 强度
            
        Returns:
            float: 新压力值 (0.0 到 1.0)
        """
        delta = 0.0
        
        if input_type in ['negative', 'threat']:
            delta = intensity * 0.2
        elif input_type == 'positive':
            delta = -intensity * 0.1
        
        new_stress = self.current_state.stress_level + delta
        return max(0.0, min(1.0, new_stress))
    
    def decay_emotion(self, decay_rate: float = 0.1) -> EmotionalState:
        """
        情绪衰减
        
        Args:
            decay_rate: 衰减率 0.0-1.0
            
        Returns:
            EmotionalState: 衰减后的状态
        """
        from datetime import datetime
        
        # 情绪强度衰减
        new_intensity = self.current_state.emotion_intensity * (1 - decay_rate)
        
        # 心情和压力自然回归中性
        new_mood = self.current_state.mood * (1 - decay_rate * 0.5)
        new_stress = self.current_state.stress_level * (1 - decay_rate * 0.5)
        
        # 如果强度很低，回归中性情绪
        new_emotion = self.current_state.primary_emotion
        if new_intensity < 0.2:
            new_emotion = EmotionType.NEUTRAL
            new_intensity = 0.1
        
        self.current_state = EmotionalState(
            primary_emotion=new_emotion,
            emotion_intensity=new_intensity,
            mood=new_mood,
            stress_level=new_stress,
            last_updated=datetime.now().isoformat()
        )
        
        return self.current_state
    
    def get_current_state(self) -> EmotionalState:
        """
        获取当前情绪状态
        
        Returns:
            EmotionalState: 当前状态
        """
        return self.current_state


# ==================== 行为决策树 ====================

@dataclass
class BehaviorDecision:
    """行为决策"""
    action: str  # 行为描述
    intensity: float  # 强度 0.0-1.0
    confidence: float  # 置信度 0.0-1.0
    emotion_influence: Dict[str, float]  # 情绪影响
    personality_influence: Dict[str, float]  # 性格影响
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'action': self.action,
            'intensity': self.intensity,
            'confidence': self.confidence,
            'emotion_influence': self.emotion_influence,
            'personality_influence': self.personality_influence
        }


class BehaviorDecisionTree:
    """行为决策树"""
    
    def __init__(
        self,
        personality: NPCPersonality,
        model_scheduler: ProviderManager
    ):
        """
        初始化行为决策树
        
        Args:
            personality: NPC性格
            model_scheduler: 模型调度器
        """
        self.personality = personality
        self.model_scheduler = model_scheduler
        self.logger = app_logger
    
    async def decide_action(
        self,
        emotional_state: EmotionalState,
        task: DispatchedTask,
        relationship_value: float = 5.0
    ) -> BehaviorDecision:
        """
        决定NPC行为
        
        Args:
            emotional_state: 情绪状态
            task: 分发的任务
            relationship_value: 关系值 (0-10)
            
        Returns:
            BehaviorDecision: 行为决策
        """
        # 分析输入
        input_type = task.input_type
        input_content = task.original_input.original_input.content
        
        # 基于规则初步决策
        rule_based_decision = self._rule_based_decision(
            emotional_state,
            input_type,
            relationship_value
        )
        
        # 使用LLM进行精炼决策
        try:
            refined_decision = await self._llm_refine_decision(
                rule_based_decision,
                emotional_state,
                input_type,
                input_content,
                relationship_value
            )
            return refined_decision
        except Exception as e:
            self.logger.warning(f"LLM决策失败，使用规则决策: {e}")
            return rule_based_decision
    
    def _rule_based_decision(
        self,
        emotional_state: EmotionalState,
        input_type: InputType,
        relationship_value: float
    ) -> BehaviorDecision:
        """
        基于规则的决策
        
        Args:
            emotional_state: 情绪状态
            input_type: 输入类型
            relationship_value: 关系值
            
        Returns:
            BehaviorDecision: 行为决策
        """
        primary_emotion = emotional_state.primary_emotion
        intensity = emotional_state.emotion_intensity
        
        # 初始化决策
        decision = BehaviorDecision(
            action="",
            intensity=intensity,
            confidence=0.7,
            emotion_influence={},
            personality_influence={}
        )
        
        # 根据情绪和输入类型决策
        if input_type == InputType.DIALOGUE:
            decision.action = self._decide_dialogue_response(
                primary_emotion, relationship_value
            )
        elif input_type == InputType.ACTION:
            decision.action = self._decide_action_response(
                primary_emotion, relationship_value
            )
        else:
            decision.action = "观察"
        
        # 记录影响
        decision.emotion_influence = {
            'primary_emotion': primary_emotion.value,
            'mood': emotional_state.mood,
            'stress': emotional_state.stress_level
        }
        decision.personality_influence = {
            'friendliness': self.personality.friendliness,
            'courage': self.personality.courage,
            'wisdom': self.personality.wisdom
        }
        
        return decision
    
    def _decide_dialogue_response(
        self,
        emotion: EmotionType,
        relationship_value: float
    ) -> str:
        """
        决定对话响应
        
        Args:
            emotion: 情绪
            relationship_value: 关系值
            
        Returns:
            str: 响应类型
        """
        # 基于关系值的反应
        if relationship_value > 7:
            # 友好关系
            if emotion in [EmotionType.JOY, EmotionType.LOVE, EmotionType.TRUST]:
                return "热情回应"
            elif emotion in [EmotionType.ANGER, EmotionType.FEAR]:
                return "关切询问"
            else:
                return "友好交谈"
        elif relationship_value < 4:
            # 冷淡关系
            if emotion in [EmotionType.ANGER, EmotionType.FEAR]:
                return "警惕回应"
            elif emotion in [EmotionType.DISGUST, EmotionType.SADNESS]:
                return "冷淡回应"
            else:
                return "简短回应"
        else:
            # 中立关系
            if emotion in [EmotionType.JOY, EmotionType.LOVE]:
                return "友善回应"
            elif emotion in [EmotionType.ANGER, EmotionType.FEAR]:
                return "谨慎回应"
            else:
                return "正常交谈"
    
    def _decide_action_response(
        self,
        emotion: EmotionType,
        relationship_value: float
    ) -> str:
        """
        决定对动作的响应
        
        Args:
            emotion: 情绪
            relationship_value: 关系值
            
        Returns:
            str: 响应类型
        """
        # 基于勇气和情绪的反应
        if self.personality.courage > 7:
            if emotion in [EmotionType.ANGER, EmotionType.FEAR]:
                return "勇敢面对"
            elif emotion in [EmotionType.JOY, EmotionType.LOVE]:
                return "积极配合"
            else:
                return "冷静观察"
        elif self.personality.courage < 4:
            if emotion in [EmotionType.FEAR, EmotionType.SADNESS]:
                return "退缩回避"
            elif emotion in [EmotionType.ANGER]:
                return "防御姿态"
            else:
                return "谨慎行事"
        else:
            return "正常反应"
    
    async def _llm_refine_decision(
        self,
        rule_decision: BehaviorDecision,
        emotional_state: EmotionalState,
        input_type: InputType,
        input_content: str,
        relationship_value: float
    ) -> BehaviorDecision:
        """
        使用LLM精炼决策
        
        Args:
            rule_decision: 规则决策
            emotional_state: 情绪状态
            input_type: 输入类型
            input_content: 输入内容
            relationship_value: 关系值
            
        Returns:
            BehaviorDecision: 精炼后的决策
        """
        prompt = f"""请根据以下信息，为NPC决定一个更具体的行为响应。

NPC性格:
- 友好度: {self.personality.friendliness}/10
- 智慧: {self.personality.wisdom}/10
- 勇气: {self.personality.courage}/10
- 贪婪: {self.personality.greed}/10

当前情绪状态:
- 主要情绪: {emotional_state.primary_emotion.value}
- 情绪强度: {emotional_state.emotion_intensity:.2f}
- 心情: {emotional_state.mood:.2f}
- 压力: {emotional_state.stress_level:.2f}

玩家输入:
- 类型: {input_type.value}
- 内容: {input_content}
- 关系值: {relationship_value}/10

初步决策: {rule_decision.action}

请以JSON格式返回：
- action: 更具体的行为描述
- intensity: 行为强度 (0.0-1.0)
- confidence: 决策置信度 (0.0-1.0)
- response_style: 回应风格（友好/冷淡/幽默/严肃等）
- additional_context: 额外的上下文说明

行为描述应该体现NPC的性格和当前情绪。
"""
        
        request_context = ProviderRequest(
            messages=[
                ChatMessage(
                    role='system',
                    content='你是行为决策专家，请根据NPC性格和情绪做出合适的行为决策。'
                ),
                ChatMessage(role='user', content=prompt)
            ],
            max_tokens=500,
            temperature=0.6
        )
        
        response = await self.model_scheduler.chat(request_context)
        
        try:
            import json
            result = json.loads(response.choices[0].message.content)
            
            return BehaviorDecision(
                action=result.get('action', rule_decision.action),
                intensity=result.get('intensity', rule_decision.intensity),
                confidence=result.get('confidence', rule_decision.confidence),
                emotion_influence=rule_decision.emotion_influence,
                personality_influence=rule_decision.personality_influence
            )
            
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"解析LLM决策失败: {e}")
            return rule_decision


# ==================== 关系值动态管理 ====================

class RelationshipManager:
    """关系值动态管理"""
    
    def __init__(
        self,
        personality: NPCPersonality,
        decay_rate: float = 0.01
    ):
        """
        初始化关系管理器
        
        Args:
            personality: NPC性格
            decay_rate: 衰减率 (每回合)
        """
        self.personality = personality
        self.decay_rate = decay_rate
        self.relationships: Dict[str, float] = {}
        self.interaction_history: Dict[str, List[Tuple[str, float]]] = {}
        self.logger = app_logger
    
    def update_relationship(
        self,
        character_id: str,
        interaction_type: str,
        attitude: str,
        emotion: str,
        context: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        更新关系值
        
        Args:
            character_id: 角色ID
            interaction_type: 交互类型 ('dialogue', 'action', 'help', 'harm')
            attitude: 态度 ('positive', 'negative', 'neutral')
            emotion: 情绪
            context: 上下文（可选）
            
        Returns:
            float: 更新后的关系值
        """
        # 计算变化值
        delta = self._calculate_relationship_delta(
            interaction_type, attitude, emotion
        )
        
        # 应用性格修正
        adjusted_delta = self._adjust_by_personality(delta, interaction_type)
        
        # 更新关系值
        current = self.relationships.get(character_id, 5.0)
        new_value = max(0.0, min(10.0, current + adjusted_delta))
        self.relationships[character_id] = new_value
        
        # 记录交互历史
        if character_id not in self.interaction_history:
            self.interaction_history[character_id] = []
        self.interaction_history[character_id].append((interaction_type, adjusted_delta))
        
        # 限制历史记录长度
        if len(self.interaction_history[character_id]) > 50:
            self.interaction_history[character_id].pop(0)
        
        self.logger.debug(
            f"关系更新: {character_id}: {current:.2f} -> {new_value:.2f} "
            f"(delta: {adjusted_delta:+.2f})"
        )
        
        return new_value
    
    def _calculate_relationship_delta(
        self,
        interaction_type: str,
        attitude: str,
        emotion: str
    ) -> float:
        """
        计算关系值变化
        
        Args:
            interaction_type: 交互类型
            attitude: 态度
            emotion: 情绪
            
        Returns:
            float: 变化值
        """
        delta = 0.0
        
        # 基于态度的基础变化
        if attitude == 'positive':
            delta = 0.5
        elif attitude == 'negative':
            delta = -0.5
        else:
            delta = 0.0
        
        # 基于交互类型调整
        if interaction_type == 'help':
            delta += 0.5
        elif interaction_type == 'harm':
            delta -= 1.0
        
        # 基于情绪调整
        if emotion in ['joy', 'love', 'trust']:
            delta += 0.3
        elif emotion in ['anger', 'fear', 'disgust']:
            delta -= 0.3
        elif emotion in ['sadness']:
            delta -= 0.1
        
        return delta
    
    def _adjust_by_personality(
        self,
        delta: float,
        interaction_type: str
    ) -> float:
        """
        根据性格调整关系值变化
        
        Args:
            delta: 原始变化值
            interaction_type: 交互类型
            
        Returns:
            float: 调整后的变化值
        """
        adjusted = delta
        
        # 友好度影响
        if self.personality.friendliness > 7:
            adjusted *= 1.2
        elif self.personality.friendliness < 4:
            adjusted *= 0.8
        
        # 贪婪影响交易相关
        if interaction_type in ['help', 'trade'] and self.personality.greed > 7:
            adjusted *= 0.9  # 贪婪者不太容易建立关系
        
        return adjusted
    
    def decay_relationships(self) -> None:
        """关系值衰减"""
        for character_id, value in self.relationships.items():
            # 向中性值(5.0)衰减
            if value > 5.0:
                self.relationships[character_id] = max(5.0, value - self.decay_rate)
            elif value < 5.0:
                self.relationships[character_id] = min(5.0, value + self.decay_rate)
    
    def get_relationship(self, character_id: str) -> float:
        """
        获取关系值
        
        Args:
            character_id: 角色ID
            
        Returns:
            float: 关系值
        """
        return self.relationships.get(character_id, 5.0)
    
    def set_relationship(self, character_id: str, value: float) -> None:
        """
        设置关系值
        
        Args:
            character_id: 角色ID
            value: 关系值
        """
        self.relationships[character_id] = max(0.0, min(10.0, value))
    
    def get_relationship_status(
        self,
        character_id: str
    ) -> str:
        """
        获取关系状态描述
        
        Args:
            character_id: 角色ID
            
        Returns:
            str: 关系状态
        """
        value = self.get_relationship(character_id)
        
        if value >= 8:
            return "亲密"
        elif value >= 6:
            return "友好"
        elif value >= 4:
            return "中立"
        elif value >= 2:
            return "冷淡"
        else:
            return "敌对"