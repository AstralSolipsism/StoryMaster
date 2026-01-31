"""
会话序列化器
负责会话状态的序列化和反序列化，包括数据压缩和校验
"""

import json
import zlib
import hashlib
from typing import Optional, Dict, Any

from ...models.session_persistence_models import (
    SessionState,
    NPCState,
    TimeManagerState
)
from ...models.dm_models import (
    GameSession,
    DMStyle,
    NarrativeTone,
    CombatDetail
)
from ...core.logging import app_logger


class SessionSerializer:
    """会话序列化器"""
    
    CURRENT_VERSION = "1.0.0"
    
    def __init__(self, compression_enabled: bool = True):
        """
        初始化序列化器
        
        Args:
            compression_enabled: 是否启用压缩
        """
        self.compression_enabled = compression_enabled
        self.version = self.CURRENT_VERSION
        self.logger = app_logger
    
    async def serialize(
        self,
        session: GameSession,
        npc_states: Optional[Dict[str, NPCState]] = None,
        time_manager_state: Optional[TimeManagerState] = None,
        event_rules: Optional[list] = None,
        custom_dm_styles: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> bytes:
        """
        序列化会话
        
        Args:
            session: 游戏会话对象
            npc_states: NPC状态字典
            time_manager_state: 时间管理器状态
            event_rules: 事件规则列表
            custom_dm_styles: 自定义DM风格
            
        Returns:
            序列化后的字节数据
        """
        try:
            # 1. 构建SessionState对象
            session_state = self._build_session_state(
                session,
                npc_states or {},
                time_manager_state,
                event_rules or [],
                custom_dm_styles or {}
            )
            
            # 2. 转换为字典
            state_dict = session_state.to_dict()
            
            # 3. 计算校验和
            checksum = self._calculate_checksum(state_dict)
            state_dict['checksum'] = checksum
            
            # 4. 转换为JSON
            json_data = json.dumps(state_dict, ensure_ascii=False)
            
            # 5. 压缩（可选）
            if self.compression_enabled:
                compressed = zlib.compress(json_data.encode('utf-8'))
                self.logger.debug(
                    f"序列化完成: {session.session_id}, "
                    f"原始大小: {len(json_data)}, "
                    f"压缩后: {len(compressed)}"
                )
                return compressed
            else:
                self.logger.debug(
                    f"序列化完成: {session.session_id}, "
                    f"大小: {len(json_data)}"
                )
                return json_data.encode('utf-8')
                
        except Exception as e:
            self.logger.error(f"序列化失败: {e}", exc_info=True)
            raise
    
    async def deserialize(
        self,
        data: bytes
    ) -> SessionState:
        """
        反序列化会话
        
        Args:
            data: 序列化的字节数据
            
        Returns:
            SessionState对象
            
        Raises:
            ValueError: 数据校验失败
        """
        try:
            # 1. 解压（如果需要）
            if self.compression_enabled:
                json_data = zlib.decompress(data).decode('utf-8')
            else:
                json_data = data.decode('utf-8')
            
            # 2. 解析JSON
            data_dict = json.loads(json_data)
            
            # 3. 验证校验和
            if 'checksum' in data_dict:
                calculated_checksum = self._calculate_checksum(data_dict)
                if calculated_checksum != data_dict['checksum']:
                    raise ValueError("数据校验失败，可能已损坏")
            
            # 4. 转换为SessionState
            session_state = SessionState.from_dict(data_dict)
            
            # 5. 验证版本
            if session_state.version != self.version:
                self.logger.warning(
                    f"版本不匹配: 文件版本={session_state.version}, "
                    f"当前版本={self.version}"
                )
                # 这里可以添加版本迁移逻辑
            
            self.logger.debug(f"反序列化完成: {session_state.session_id}")
            return session_state
            
        except Exception as e:
            self.logger.error(f"反序列化失败: {e}", exc_info=True)
            raise
    
    def _build_session_state(
        self,
        session: GameSession,
        npc_states: Dict[str, NPCState],
        time_manager_state: Optional[TimeManagerState],
        event_rules: list,
        custom_dm_styles: Dict[str, Dict[str, Any]]
    ) -> SessionState:
        """
        构建SessionState对象
        
        Args:
            session: 游戏会话对象
            npc_states: NPC状态字典
            time_manager_state: 时间管理器状态
            event_rules: 事件规则列表
            custom_dm_styles: 自定义DM风格
            
        Returns:
            SessionState对象
        """
        # 如果没有提供时间管理器状态，创建一个默认的
        if not time_manager_state:
            from datetime import datetime
            time_manager_state = TimeManagerState(
                current_time=session.current_time,
                session_time_start=session.created_at,
                registered_events=[]
            )
        
        # 处理DM风格枚举
        dm_style_value = session.dm_style
        if isinstance(session.dm_style, DMStyle):
            dm_style_value = session.dm_style.value
        
        narrative_tone_value = session.narrative_tone
        if isinstance(session.narrative_tone, NarrativeTone):
            narrative_tone_value = session.narrative_tone.value
        
        combat_detail_value = session.combat_detail
        if isinstance(session.combat_detail, CombatDetail):
            combat_detail_value = session.combat_detail.value
        
        return SessionState(
            session_id=session.session_id,
            dm_id=session.dm_id,
            campaign_id=session.campaign_id,
            name=session.name,
            description=session.description,
            current_time=session.current_time,
            created_at=session.created_at,
            updated_at=session.updated_at,
            current_scene_id=session.current_scene_id,
            player_characters=session.player_characters,
            active_npcs=session.active_npcs,
            dm_style=dm_style_value,
            narrative_tone=narrative_tone_value,
            combat_detail=combat_detail_value,
            custom_dm_style=session.custom_dm_style,
            custom_system_prompt=session.custom_system_prompt,
            npc_states=npc_states,
            time_manager_state=time_manager_state,
            event_rules=[rule.to_dict() if hasattr(rule, 'to_dict') else rule for rule in event_rules],
            custom_dm_styles=custom_dm_styles,
            version=self.version
        )
    
    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """
        计算数据校验和
        
        Args:
            data: 数据字典
            
        Returns:
            SHA256校验和
        """
        data_copy = data.copy()
        if 'checksum' in data_copy:
            del data_copy['checksum']
        json_str = json.dumps(data_copy, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()


class VersionManager:
    """版本管理器"""
    
    CURRENT_VERSION = "1.0.0"
    
    def __init__(self):
        """初始化版本管理器"""
        # 定义版本迁移规则
        self.migrations = {
            # future migrations will be added here
        }
    
    async def migrate(
        self,
        session_state: SessionState,
        target_version: Optional[str] = None
    ) -> SessionState:
        """
        版本迁移
        
        Args:
            session_state: 会话状态
            target_version: 目标版本，None表示迁移到最新版本
            
        Returns:
            迁移后的会话状态
        """
        if target_version is None:
            target_version = self.CURRENT_VERSION
        
        current_version = session_state.version
        
        if current_version == target_version:
            return session_state
        
        # 如果已经是最新版本，不需要迁移
        if current_version == self.CURRENT_VERSION:
            return session_state
        
        # 执行迁移
        # 这里可以实现版本间的数据转换逻辑
        app_logger.info(
            f"迁移会话 {session_state.session_id} "
            f"从版本 {current_version} 到 {target_version}"
        )
        
        return session_state
    
    def validate_compatibility(
        self,
        version: str
    ) -> bool:
        """
        验证版本兼容性
        
        Args:
            version: 版本号
            
        Returns:
            是否兼容
        """
        # 简单的版本比较逻辑
        # 主版本号必须匹配，次版本号可以向下兼容
        current_major = int(self.CURRENT_VERSION.split('.')[0])
        version_major = int(version.split('.')[0])
        
        return version_major == current_major