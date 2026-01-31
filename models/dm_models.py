"""
DM模块数据模型
定义DM智能体、NPC、游戏会话等相关的数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from enum import Enum


# ==================== 枚举类型 ====================

class InputType(Enum):
    """玩家输入类型"""
    ACTION = "action"           # 行为描述（施法、鉴定、移动等）
    DIALOGUE = "dialogue"       # 对话内容（角色发言）
    THOUGHT = "thought"         # 心理描述
    OOC = "ooc"                # 场外发言（玩家间交流）
    COMMAND = "command"          # 指令（/回合结束、/施法等）


class DMStyle(Enum):
    """DM风格"""
    BALANCED = "balanced"       # 平衡
    SERIOUS = "serious"         # 严肃
    HUMOROUS = "humorous"       # 幽默
    HORROR = "horror"           # 恐怖
    DRAMATIC = "dramatic"       # 戏剧性
    CUSTOM = "custom"           # 自定义


class NarrativeTone(Enum):
    """叙述基调"""
    DESCRIPTIVE = "descriptive"   # 描述性
    CONCISE = "concise"          # 简洁
    DETAILED = "detailed"        # 详细


class CombatDetail(Enum):
    """战斗细节程度"""
    MINIMAL = "minimal"       # 最小
    NORMAL = "normal"         # 正常
    DETAILED = "detailed"      # 详细


class EventTriggerType(Enum):
    """事件触发类型"""
    TIME_BASED = "time_based"       # 基于时间
    CONDITION_BASED = "condition"    # 基于条件
    PLAYER_ACTION = "player_action"   # 基于玩家动作


# ==================== 玩家输入相关 ====================

@dataclass
class PlayerInput:
    """玩家输入"""
    character_id: str
    character_name: str
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'character_id': self.character_id,
            'character_name': self.character_name,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


@dataclass
class ClassifiedInput:
    """分类后的输入"""
    original_input: PlayerInput
    input_type: InputType
    confidence: float
    entities: List[Dict[str, Any]] = field(default_factory=list)
    action_type: Optional[str] = None
    target: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'input_type': self.input_type.value,
            'confidence': self.confidence,
            'entities': self.entities,
            'action_type': self.action_type,
            'target': self.target
        }


# ==================== 实体抽取相关 ====================

@dataclass
class EntityExtraction:
    """实体抽取结果"""
    entity_type: str
    name: str
    context: str
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'entity_type': self.entity_type,
            'name': self.name,
            'context': self.context,
            'confidence': self.confidence
        }


@dataclass
class MatchedEntity:
    """匹配后的实体"""
    extraction: EntityExtraction
    matched_entity: Optional[Any]  # Entity对象
    confidence: float
    is_new: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'extraction': self.extraction.to_dict(),
            'matched_entity_id': self.matched_entity.id if self.matched_entity else None,
            'confidence': self.confidence,
            'is_new': self.is_new
        }


@dataclass
class ExtractedEntity:
    """抽取的实体集合"""
    original_input: ClassifiedInput
    entities: List[MatchedEntity]
    
    def get_entities_by_type(self, entity_type: str) -> List[MatchedEntity]:
        """根据类型获取实体"""
        return [e for e in self.entities 
                if e.extraction.entity_type == entity_type]
    
    def get_new_entities(self) -> List[MatchedEntity]:
        """获取新实体"""
        return [e for e in self.entities if e.is_new]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'entities': [e.to_dict() for e in self.entities]
        }


# ==================== 任务相关 ====================

@dataclass
class TaskData:
    """任务数据基类"""
    pass


@dataclass
class ActionTaskData(TaskData):
    """动作任务数据"""
    action_type: str
    target: Optional[Dict[str, Any]]
    involved_entities: List[MatchedEntity]
    result: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'action_type': self.action_type,
            'target': self.target,
            'entities': [e.to_dict() for e in self.involved_entities],
            'result': self.result
        }


@dataclass
class DialogueTaskData(TaskData):
    """对话任务数据"""
    speaker: str
    content: str
    target: Optional[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'speaker': self.speaker,
            'content': self.content,
            'target': self.target
        }


@dataclass
class ThoughtTaskData(TaskData):
    """心理描述任务数据"""
    character: str
    content: str
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'character': self.character,
            'content': self.content
        }


@dataclass
class OCCTaskData(TaskData):
    """场外发言任务数据"""
    player: str
    content: str
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'player': self.player,
            'content': self.content
        }


@dataclass
class CommandTaskData(TaskData):
    """指令任务数据"""
    command: str
    arguments: List[str]
    raw_input: str
    parsed_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'command': self.command,
            'arguments': self.arguments,
            'raw_input': self.raw_input,
            'parsed_data': self.parsed_data
        }


@dataclass
class DispatchedTask:
    """分发的任务"""
    task_id: str
    input_type: InputType
    original_input: ClassifiedInput
    entities: ExtractedEntity
    task_data: Union[ActionTaskData, DialogueTaskData, ThoughtTaskData, 
                     OCCTaskData, CommandTaskData]
    requires_npc_response: bool
    target_npc_id: Optional[str]
    time_cost: timedelta
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        task_data_dict = None
        if self.task_data:
            task_data_dict = self.task_data.to_dict()
        
        return {
            'task_id': self.task_id,
            'input_type': self.input_type.value,
            'entities': self.entities.to_dict(),
            'task_data': task_data_dict,
            'requires_npc_response': self.requires_npc_response,
            'target_npc_id': self.target_npc_id,
            'time_cost': self.time_cost.total_seconds()
        }


# ==================== NPC相关 ====================

@dataclass
class NPCPersonality:
    """NPC性格"""
    friendliness: float = 5.0      # 友好度 (0-10)
    wisdom: float = 5.0            # 智慧 (0-10)
    courage: float = 5.0          # 勇气 (0-10)
    greed: float = 5.0              # 贪婪 (0-10)
    speech_style: str = "正常"       # 说话风格
    speech_pattern: str = "直接"     # 说话方式
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'friendliness': self.friendliness,
            'wisdom': self.wisdom,
            'courage': self.courage,
            'greed': self.greed,
            'speech_style': self.speech_style,
            'speech_pattern': self.speech_pattern
        }


@dataclass
class Memory:
    """记忆"""
    timestamp: datetime
    interaction: str
    response: str
    emotion: str
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'interaction': self.interaction,
            'response': self.response,
            'emotion': self.emotion,
            'summary': self.summary
        }


@dataclass
class NPCResponse:
    """NPC响应"""
    npc_id: str
    response: str
    action: str
    emotion: str
    attitude: str  # positive, negative, neutral
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'npc_id': self.npc_id,
            'response': self.response,
            'action': self.action,
            'emotion': self.emotion,
            'attitude': self.attitude
        }


# ==================== 游戏事件相关 ====================

@dataclass
class GameEvent:
    """游戏事件"""
    event_id: str
    event_type: str
    description: str
    effects: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'description': self.description,
            'effects': self.effects,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class EventRule:
    """事件规则"""
    rule_id: str
    name: str
    trigger_type: EventTriggerType
    condition: Dict[str, Any]
    event_data: Dict[str, Any]
    enabled: bool = True
    priority: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'rule_id': self.rule_id,
            'name': self.name,
            'trigger_type': self.trigger_type.value,
            'condition': self.condition,
            'event_data': self.event_data,
            'enabled': self.enabled,
            'priority': self.priority
        }


# ==================== DM响应相关 ====================

@dataclass
class PerceptibleInfo:
    """可感知信息"""
    player_actions: List[str]
    npc_responses: Dict[str, NPCResponse]
    events: List[GameEvent]
    scene_description: str
    changed_entities: List[MatchedEntity]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'player_actions': self.player_actions,
            'npc_responses': {k: v.to_dict() for k, v in self.npc_responses.items()},
            'events': [e.to_dict() for e in self.events],
            'scene_description': self.scene_description,
            'changed_entities': [e.to_dict() for e in self.changed_entities]
        }


@dataclass
class DMResponse:
    """DM响应"""
    content: str
    timestamp: datetime
    style: DMStyle
    tone: NarrativeTone
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'style': self.style.value,
            'tone': self.tone.value,
            'metadata': self.metadata
        }


# ==================== 游戏会话相关 ====================

@dataclass
class GameSession:
    """游戏会话"""
    session_id: str
    dm_id: str
    campaign_id: Optional[str]
    name: str
    description: str
    current_time: datetime
    current_scene_id: Optional[str]
    player_characters: List[str]  # character_ids
    active_npcs: List[str]  # npc_ids
    created_at: datetime
    updated_at: datetime
    dm_style: DMStyle = DMStyle.BALANCED
    narrative_tone: NarrativeTone = NarrativeTone.DESCRIPTIVE
    combat_detail: CombatDetail = CombatDetail.NORMAL
    custom_dm_style: Optional[str] = None  # 自定义DM风格
    custom_system_prompt: Optional[str] = None  # 自定义系统提示
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'session_id': self.session_id,
            'dm_id': self.dm_id,
            'campaign_id': self.campaign_id,
            'name': self.name,
            'description': self.description,
            'current_time': self.current_time.isoformat(),
            'current_scene_id': self.current_scene_id,
            'player_characters': self.player_characters,
            'active_npcs': self.active_npcs,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'dm_style': self.dm_style.value,
            'narrative_tone': self.narrative_tone.value,
            'combat_detail': self.combat_detail.value,
            'custom_dm_style': self.custom_dm_style,
            'custom_system_prompt': self.custom_system_prompt
        }


# ==================== DM配置相关 ====================

@dataclass
class DMConfig:
    """DM智能体配置"""
    # 基础配置
    agent_id: str
    agent_type: str = "dm"
    version: str = "1.0.0"
    
    # DM风格配置
    dm_style: DMStyle = DMStyle.BALANCED
    narrative_tone: NarrativeTone = NarrativeTone.DESCRIPTIVE
    combat_detail: CombatDetail = CombatDetail.NORMAL
    custom_dm_style: Optional[str] = None  # 自定义DM风格描述
    custom_system_prompt: Optional[str] = None  # 自定义系统提示
    
    # 游戏规则配置
    rule_system: str = "dnd_5e"  # 支持的规则系统
    strict_mode: bool = False  # 严格规则模式
    
    # 响应配置
    max_response_length: int = 2000
    include_dice_results: bool = True
    auto_advance_plot: bool = False
    
    # 推理配置
    reasoning_mode: str = "chain_of_thought"
    reasoning_config: Dict[str, Any] = field(default_factory=dict)
    
    # 工具配置
    enabled_tools: List[str] = field(default_factory=list)
    tool_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # 性能配置
    max_execution_time: float = 300.0
    max_memory_usage: int = 2048
    concurrency_limit: int = 5
    
    # 模型配置
    max_tokens: int = 2000
    temperature: float = 0.7
    system_prompt: Optional[str] = None
    
    # 个性化配置
    personality: Optional[Dict[str, float]] = None
    behavior_patterns: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'version': self.version,
            'dm_style': self.dm_style.value,
            'narrative_tone': self.narrative_tone.value,
            'combat_detail': self.combat_detail.value,
            'custom_dm_style': self.custom_dm_style,
            'custom_system_prompt': self.custom_system_prompt,
            'rule_system': self.rule_system,
            'strict_mode': self.strict_mode,
            'max_response_length': self.max_response_length,
            'include_dice_results': self.include_dice_results,
            'auto_advance_plot': self.auto_advance_plot,
            'reasoning_mode': self.reasoning_mode,
            'reasoning_config': self.reasoning_config,
            'enabled_tools': self.enabled_tools,
            'tool_config': self.tool_config,
            'max_execution_time': self.max_execution_time,
            'max_memory_usage': self.max_memory_usage,
            'concurrency_limit': self.concurrency_limit,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'system_prompt': self.system_prompt,
            'personality': self.personality,
            'behavior_patterns': self.behavior_patterns
        }
    
    def get_effective_system_prompt(self) -> str:
        """获取有效的系统提示词"""
        if self.custom_system_prompt:
            return self.custom_system_prompt
        return self.system_prompt
    
    def get_effective_dm_style(self) -> DMStyle:
        """获取有效的DM风格"""
        if self.custom_dm_style:
            return DMStyle.CUSTOM
        return self.dm_style


# ==================== 自定义DM风格请求 ====================

@dataclass
class CustomDMStyleRequest:
    """自定义DM风格请求"""
    style_name: str
    style_description: str
    system_prompt: Optional[str] = None
    narrative_tone: NarrativeTone = NarrativeTone.DESCRIPTIVE
    combat_detail: CombatDetail = CombatDetail.NORMAL
    temperature: float = 0.7
    examples: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'style_name': self.style_name,
            'style_description': self.style_description,
            'system_prompt': self.system_prompt,
            'narrative_tone': self.narrative_tone.value,
            'combat_detail': self.combat_detail.value,
            'temperature': self.temperature,
            'examples': self.examples
        }


# ==================== 工具函数 ====================

def create_dm_config(
    agent_id: str,
    dm_style: DMStyle = DMStyle.BALANCED,
    narrative_tone: NarrativeTone = NarrativeTone.DESCRIPTIVE,
    combat_detail: CombatDetail = CombatDetail.NORMAL,
    custom_dm_style: Optional[str] = None,
    custom_system_prompt: Optional[str] = None,
    **kwargs
) -> DMConfig:
    """创建DM配置"""
    return DMConfig(
        agent_id=agent_id,
        dm_style=dm_style,
        narrative_tone=narrative_tone,
        combat_detail=combat_detail,
        custom_dm_style=custom_dm_style,
        custom_system_prompt=custom_system_prompt,
        **kwargs
    )


def create_player_input(
    character_id: str,
    character_name: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None
) -> PlayerInput:
    """创建玩家输入"""
    return PlayerInput(
        character_id=character_id,
        character_name=character_name,
        content=content,
        timestamp=datetime.now(),
        metadata=metadata or {}
    )


def create_game_session(
    session_id: str,
    dm_id: str,
    name: str,
    description: str,
    campaign_id: Optional[str] = None,
    npc_ids: Optional[List[str]] = None
) -> GameSession:
    """创建游戏会话"""
    now = datetime.now()
    return GameSession(
        session_id=session_id,
        dm_id=dm_id,
        campaign_id=campaign_id,
        name=name,
        description=description,
        current_time=now,
        current_scene_id=None,
        player_characters=[],
        active_npcs=npc_ids or [],
        created_at=now,
        updated_at=now
    )


def get_dm_style_from_string(style_str: str) -> DMStyle:
    """从字符串获取DM风格"""
    try:
        return DMStyle(style_str)
    except ValueError:
        return DMStyle.CUSTOM


def create_custom_dm_style_request(
    style_name: str,
    style_description: str,
    system_prompt: Optional[str] = None,
    **kwargs
) -> CustomDMStyleRequest:
    """创建自定义DM风格请求"""
    return CustomDMStyleRequest(
        style_name=style_name,
        style_description=style_description,
        system_prompt=system_prompt,
        **kwargs
    )


# ==================== 预定义DM风格示例 ====================

PREDEFINED_DM_STYLES = {
    "黑暗史诗": {
        "style_name": "黑暗史诗",
        "style_description": "采用史诗般的叙事风格，营造宏大、庄严的氛围。语言庄严，充满戏剧张力。",
        "system_prompt": "你是一个采用史诗叙事风格的DM。你的语言应该庄严、宏大，充满戏剧性和史诗感。在描述场景和事件时，要强调历史感、英雄气概和命运的庄严感。",
        "narrative_tone": NarrativeTone.DESCRIPTIVE,
        "combat_detail": CombatDetail.DETAILED,
        "temperature": 0.6
    },
    "轻松幽默": {
        "style_name": "轻松幽默",
        "style_description": "采用轻松幽默的叙事风格，营造愉快、有趣的氛围。语言轻松，充满幽默和机智。",
        "system_prompt": "你是一个采用轻松幽默风格的DM。你的语言应该轻松、愉快，充满幽默和机智。在描述场景和事件时，要加入一些幽默元素，让玩家感到轻松愉快。适度使用网络流行语和梗，但不要过度。",
        "narrative_tone": NarrativeTone.CONCISE,
        "combat_detail": CombatDetail.MINIMAL,
        "temperature": 0.9
    },
    "悬疑推理": {
        "style_name": "悬疑推理",
        "style_description": "采用悬疑推理的叙事风格，营造神秘、紧张的氛围。语言简洁，充满线索和谜题。",
        "system_prompt": "你是一个采用悬疑推理风格的DM。你的语言应该简洁、充满线索和谜题，营造神秘和紧张的氛围。在描述场景和事件时，要提供详细的线索，引导玩家进行推理和解谜。不要直接揭示答案，让玩家自己发现真相。",
        "narrative_tone": NarrativeTone.CONCISE,
        "combat_detail": CombatDetail.NORMAL,
        "temperature": 0.5
    },
    "沉浸式恐怖": {
        "style_name": "沉浸式恐怖",
        "style_description": "采用沉浸式恐怖的叙事风格，营造真实、恐怖的氛围。语言细腻，充满感官描述。",
        "system_prompt": "你是一个采用沉浸式恐怖风格的DM。你的语言应该细腻、充满感官描述（视觉、听觉、嗅觉、触觉），营造真实、恐怖的氛围。在描述场景和事件时，要强调恐怖元素，让玩家感到真正的恐惧。使用克苏鲁式恐怖小说的描述风格，注重细节和氛围。",
        "narrative_tone": NarrativeTone.DETAILED,
        "combat_detail": CombatDetail.DETAILED,
        "temperature": 0.6
    }
}


def get_predefined_dm_style(style_name: str) -> Optional[CustomDMStyleRequest]:
    """获取预定义的DM风格"""
    return PREDEFINED_DM_STYLES.get(style_name)


# ==================== 记忆管理相关 ====================

@dataclass
class SceneMemory:
    """场景记忆"""
    memory_id: str
    session_id: str
    scene_id: str
    event_type: str  # 'state_change', 'interaction', 'environment', 'discovery'
    timestamp: datetime
    description: str
    involved_entities: List[str] = field(default_factory=list)  # entity_ids
    state_changes: Dict[str, Any] = field(default_factory=dict)
    related_scene_ids: List[str] = field(default_factory=list)
    importance: float = 0.5  # 0-1
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'memory_id': self.memory_id,
            'session_id': self.session_id,
            'scene_id': self.scene_id,
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat(),
            'description': self.description,
            'involved_entities': self.involved_entities,
            'state_changes': self.state_changes,
            'related_scene_ids': self.related_scene_ids,
            'importance': self.importance,
            'tags': self.tags
        }


@dataclass
class HistoryMemory:
    """历史记忆"""
    memory_id: str
    session_id: str
    timestamp: datetime
    event_type: str  # 'player_action', 'npc_response', 'dm_narration', 'system_event'
    content: str
    participants: List[str] = field(default_factory=list)  # character_ids, npc_ids
    location: Optional[str] = None  # scene_id
    summary: str = ""
    importance: float = 0.5  # 0-1
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'memory_id': self.memory_id,
            'session_id': self.session_id,
            'timestamp': self.timestamp.isoformat(),
            'event_type': self.event_type,
            'content': self.content,
            'participants': self.participants,
            'location': self.location,
            'summary': self.summary,
            'importance': self.importance,
            'tags': self.tags,
            'metadata': self.metadata
        }


@dataclass
class NPCMemoryRecord:
    """NPC记忆记录（用于持久化）"""
    record_id: str
    npc_id: str
    session_id: str
    timestamp: datetime
    interaction: str
    response: str
    emotion: str
    attitude: str
    character_id: Optional[str] = None
    summary: str = ""
    importance: float = 0.5  # 0-1
    relationship_delta: float = 0.0
    compressed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'record_id': self.record_id,
            'npc_id': self.npc_id,
            'session_id': self.session_id,
            'timestamp': self.timestamp.isoformat(),
            'interaction': self.interaction,
            'response': self.response,
            'emotion': self.emotion,
            'attitude': self.attitude,
            'character_id': self.character_id,
            'summary': self.summary,
            'importance': self.importance,
            'relationship_delta': self.relationship_delta,
            'compressed': self.compressed,
            'metadata': self.metadata
        }


@dataclass
class MemorySearchQuery:
    """记忆搜索查询"""
    session_id: str
    query_text: str
    memory_types: Optional[List[str]] = None  # 'scene', 'history', 'npc'
    entity_ids: Optional[List[str]] = None
    scene_ids: Optional[List[str]] = None
    npc_ids: Optional[List[str]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    tags: Optional[List[str]] = None
    min_importance: float = 0.0
    limit: int = 10
    include_compressed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'session_id': self.session_id,
            'query_text': self.query_text,
            'memory_types': self.memory_types,
            'entity_ids': self.entity_ids,
            'scene_ids': self.scene_ids,
            'npc_ids': self.npc_ids,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'tags': self.tags,
            'min_importance': self.min_importance,
            'limit': self.limit,
            'include_compressed': self.include_compressed
        }


@dataclass
class MemorySearchResult:
    """记忆搜索结果"""
    memory_id: str
    memory_type: str  # 'scene', 'history', 'npc'
    content: str
    relevance_score: float  # 0-1
    importance: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'memory_id': self.memory_id,
            'memory_type': self.memory_type,
            'content': self.content,
            'relevance_score': self.relevance_score,
            'importance': self.importance,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }