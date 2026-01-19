"""
DM服务模块
提供DM智能体、NPC智能体等核心服务
"""

from .input_classifier import InputClassifier, create_input_classifier
from .entity_extractor import EntityExtractor, create_entity_extractor
from .task_dispatcher import (
    TaskDispatcher,
    TaskProcessor,
    ActionProcessor,
    DialogueProcessor,
    ThoughtProcessor,
    OOCProcessor,
    CommandProcessor,
    create_task_dispatcher
)
from .npc_agent import NPCAgent, NPCMemory, create_npc_agent
from .npc_pool import NPCAgentPool, create_npc_pool
from .time_manager import (
    TimeManager,
    EventRuleBase,
    SpellSlotRecoveryEvent,
    HolidayEvent,
    CustomEventRule,
    create_time_manager,
    create_spell_recovery_event,
    create_holiday_event,
    create_custom_event_rule
)
from .response_generator import (
    ResponseGenerator,
    DMStylesConfig,
    create_response_generator
)

__all__ = [
    # 输入分类器
    'InputClassifier',
    'create_input_classifier',
    
    # 实体抽取器
    'EntityExtractor',
    'create_entity_extractor',
    
    # 任务分发器
    'TaskDispatcher',
    'TaskProcessor',
    'ActionProcessor',
    'DialogueProcessor',
    'ThoughtProcessor',
    'OOCProcessor',
    'CommandProcessor',
    'create_task_dispatcher',
    
    # NPC智能体
    'NPCAgent',
    'NPCMemory',
    'create_npc_agent',
    
    # NPC智能体池
    'NPCAgentPool',
    'create_npc_pool',
    
    # 时间管理器
    'TimeManager',
    'EventRuleBase',
    'SpellSlotRecoveryEvent',
    'HolidayEvent',
    'CustomEventRule',
    'create_time_manager',
    'create_spell_recovery_event',
    'create_holiday_event',
    'create_custom_event_rule',
    
    # 响应生成器
    'ResponseGenerator',
    'DMStylesConfig',
    'create_response_generator',
    
    # DM核心智能体
    'DMAgent',
    'create_dm_agent',
]