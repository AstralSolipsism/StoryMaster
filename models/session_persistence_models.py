"""
会话持久化相关数据模型
定义会话状态、快照、回滚日志等数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class SnapshotTrigger(Enum):
    """快照触发类型"""
    MANUAL = "manual"          # 手动创建
    AUTO_SAVE = "auto_save"    # 自动保存
    BEFORE_ROLLBACK = "before_rollback"  # 回滚前
    EVENT_TRIGGERED = "event_triggered"  # 事件触发


@dataclass
class NPCState:
    """NPC状态"""
    npc_id: str
    personality: Dict[str, float]
    emotions: Dict[str, float]
    memory_summary: List[Dict[str, Any]]
    relationships: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'npc_id': self.npc_id,
            'personality': self.personality,
            'emotions': self.emotions,
            'memory_summary': self.memory_summary,
            'relationships': self.relationships
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NPCState':
        """从字典创建"""
        return cls(
            npc_id=data['npc_id'],
            personality=data['personality'],
            emotions=data['emotions'],
            memory_summary=data.get('memory_summary', []),
            relationships=data.get('relationships', {})
        )


@dataclass
class TimeManagerState:
    """时间管理器状态"""
    current_time: datetime
    session_time_start: datetime
    registered_events: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'current_time': self.current_time.isoformat(),
            'session_time_start': self.session_time_start.isoformat(),
            'registered_events': self.registered_events
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimeManagerState':
        """从字典创建"""
        return cls(
            current_time=datetime.fromisoformat(data['current_time']),
            session_time_start=datetime.fromisoformat(data['session_time_start']),
            registered_events=data.get('registered_events', [])
        )


@dataclass
class SessionState:
    """会话状态（完整序列化对象）"""
    session_id: str
    dm_id: str
    campaign_id: Optional[str]
    name: str
    description: str
    current_time: datetime
    created_at: datetime
    updated_at: datetime
    current_scene_id: Optional[str]
    player_characters: List[str]
    active_npcs: List[str]
    dm_style: str
    narrative_tone: str
    combat_detail: str
    custom_dm_style: Optional[str]
    custom_system_prompt: Optional[str]
    npc_states: Dict[str, NPCState]
    time_manager_state: TimeManagerState
    event_rules: List[Dict[str, Any]]
    custom_dm_styles: Dict[str, Dict[str, Any]]
    version: str = "1.0.0"
    checksum: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'session_id': self.session_id,
            'dm_id': self.dm_id,
            'campaign_id': self.campaign_id,
            'name': self.name,
            'description': self.description,
            'current_time': self.current_time.isoformat(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'current_scene_id': self.current_scene_id,
            'player_characters': self.player_characters,
            'active_npcs': self.active_npcs,
            'dm_style': self.dm_style,
            'narrative_tone': self.narrative_tone,
            'combat_detail': self.combat_detail,
            'custom_dm_style': self.custom_dm_style,
            'custom_system_prompt': self.custom_system_prompt,
            'npc_states': {k: v.to_dict() for k, v in self.npc_states.items()},
            'time_manager_state': self.time_manager_state.to_dict(),
            'event_rules': self.event_rules,
            'custom_dm_styles': self.custom_dm_styles,
            'version': self.version,
            'checksum': self.checksum
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionState':
        """从字典创建"""
        return cls(
            session_id=data['session_id'],
            dm_id=data['dm_id'],
            campaign_id=data.get('campaign_id'),
            name=data['name'],
            description=data['description'],
            current_time=datetime.fromisoformat(data['current_time']),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            current_scene_id=data.get('current_scene_id'),
            player_characters=data['player_characters'],
            active_npcs=data['active_npcs'],
            dm_style=data['dm_style'],
            narrative_tone=data['narrative_tone'],
            combat_detail=data['combat_detail'],
            custom_dm_style=data.get('custom_dm_style'),
            custom_system_prompt=data.get('custom_system_prompt'),
            npc_states={k: NPCState.from_dict(v) for k, v in data['npc_states'].items()},
            time_manager_state=TimeManagerState.from_dict(data['time_manager_state']),
            event_rules=data.get('event_rules', []),
            custom_dm_styles=data.get('custom_dm_styles', {}),
            version=data.get('version', '1.0.0'),
            checksum=data.get('checksum')
        )


@dataclass
class SessionSnapshot:
    """会话快照"""
    snapshot_id: str
    session_id: str
    name: str
    description: Optional[str]
    created_at: datetime
    created_by: str
    session_state: SessionState
    tags: List[str]
    is_auto: bool
    trigger_type: str = SnapshotTrigger.MANUAL.value
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'snapshot_id': self.snapshot_id,
            'session_id': self.session_id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by,
            'session_state': self.session_state.to_dict(),
            'tags': self.tags,
            'is_auto': self.is_auto,
            'trigger_type': self.trigger_type
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionSnapshot':
        """从字典创建"""
        return cls(
            snapshot_id=data['snapshot_id'],
            session_id=data['session_id'],
            name=data['name'],
            description=data.get('description'),
            created_at=datetime.fromisoformat(data['created_at']),
            created_by=data['created_by'],
            session_state=SessionState.from_dict(data['session_state']),
            tags=data.get('tags', []),
            is_auto=data.get('is_auto', False),
            trigger_type=data.get('trigger_type', SnapshotTrigger.MANUAL.value)
        )


@dataclass
class RollbackLog:
    """回滚日志"""
    log_id: str
    session_id: str
    snapshot_id: Optional[str]
    timestamp: datetime
    action: str  # 'create_point', 'rollback'
    operator: str
    before_state: Dict[str, Any]
    after_state: Dict[str, Any]
    conflicts: List[Dict[str, Any]]
    resolution: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'log_id': self.log_id,
            'session_id': self.session_id,
            'snapshot_id': self.snapshot_id,
            'timestamp': self.timestamp.isoformat(),
            'action': self.action,
            'operator': self.operator,
            'before_state': self.before_state,
            'after_state': self.after_state,
            'conflicts': self.conflicts,
            'resolution': self.resolution
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RollbackLog':
        """从字典创建"""
        return cls(
            log_id=data['log_id'],
            session_id=data['session_id'],
            snapshot_id=data.get('snapshot_id'),
            timestamp=datetime.fromisoformat(data['timestamp']),
            action=data['action'],
            operator=data['operator'],
            before_state=data['before_state'],
            after_state=data['after_state'],
            conflicts=data.get('conflicts', []),
            resolution=data.get('resolution')
        )