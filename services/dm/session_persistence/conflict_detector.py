"""
冲突检测器
检测会话状态之间的冲突，用于回滚操作前的风险评估
"""

from typing import Dict, Any, List
from datetime import datetime

from ...models.session_persistence_models import SessionState
from ...core.logging import app_logger


class ConflictDetector:
    """冲突检测器"""
    
    async def detect_conflicts(
        self,
        current_state: SessionState,
        target_state: SessionState
    ) -> List[Dict[str, Any]]:
        """
        检测状态之间的冲突
        
        Args:
            current_state: 当前会话状态
            target_state: 目标会话状态
            
        Returns:
            冲突列表
        """
        conflicts = []
        
        # 1. 检查时间冲突
        if await self._detect_time_conflict(current_state, target_state):
            conflicts.append({
                'type': 'time_conflict',
                'severity': 'warning',
                'description': '目标状态的时间早于当前状态',
                'current': current_state.current_time.isoformat(),
                'target': target_state.current_time.isoformat()
            })
        
        # 2. 检查参与者冲突
        player_conflicts = await self._detect_player_conflicts(current_state, target_state)
        if player_conflicts:
            conflicts.extend(player_conflicts)
        
        # 3. 检查NPC冲突
        npc_conflicts = await self._detect_npc_conflicts(current_state, target_state)
        if npc_conflicts:
            conflicts.extend(npc_conflicts)
        
        # 4. 检查场景冲突
        if await self._detect_scene_conflict(current_state, target_state):
            conflicts.append({
                'type': 'scene_conflict',
                'severity': 'warning',
                'description': '当前场景不一致',
                'current': current_state.current_scene_id,
                'target': target_state.current_scene_id
            })
        
        # 5. 检查DM风格冲突
        if await self._detect_style_conflict(current_state, target_state):
            conflicts.append({
                'type': 'style_conflict',
                'severity': 'info',
                'description': 'DM风格配置不一致',
                'current': {
                    'dm_style': current_state.dm_style,
                    'narrative_tone': current_state.narrative_tone,
                    'combat_detail': current_state.combat_detail
                },
                'target': {
                    'dm_style': target_state.dm_style,
                    'narrative_tone': target_state.narrative_tone,
                    'combat_detail': target_state.combat_detail
                }
            })
        
        if conflicts:
            app_logger.warning(
                f"检测到 {len(conflicts)} 个冲突: {current_state.session_id}"
            )
        else:
            app_logger.debug(
                f"未检测到冲突: {current_state.session_id}"
            )
        
        return conflicts
    
    async def _detect_time_conflict(
        self,
        current_state: SessionState,
        target_state: SessionState
    ) -> bool:
        """
        检测时间冲突
        
        Args:
            current_state: 当前会话状态
            target_state: 目标会话状态
            
        Returns:
            是否存在时间冲突
        """
        return current_state.current_time > target_state.current_time
    
    async def _detect_player_conflicts(
        self,
        current_state: SessionState,
        target_state: SessionState
    ) -> List[Dict[str, Any]]:
        """
        检测玩家角色冲突
        
        Args:
            current_state: 当前会话状态
            target_state: 目标会话状态
            
        Returns:
            冲突列表
        """
        conflicts = []
        
        current_players = set(current_state.player_characters)
        target_players = set(target_state.player_characters)
        
        # 检查移除的玩家
        removed_players = current_players - target_players
        if removed_players:
            conflicts.append({
                'type': 'player_removed',
                'severity': 'info',
                'description': f'目标状态中不包含以下玩家: {", ".join(removed_players)}',
                'players': list(removed_players)
            })
        
        # 检查新增的玩家
        added_players = target_players - current_players
        if added_players:
            conflicts.append({
                'type': 'player_added',
                'severity': 'info',
                'description': f'目标状态中包含以下新玩家: {", ".join(added_players)}',
                'players': list(added_players)
            })
        
        return conflicts
    
    async def _detect_npc_conflicts(
        self,
        current_state: SessionState,
        target_state: SessionState
    ) -> List[Dict[str, Any]]:
        """
        检测NPC冲突
        
        Args:
            current_state: 当前会话状态
            target_state: 目标会话状态
            
        Returns:
            冲突列表
        """
        conflicts = []
        
        current_npcs = set(current_state.active_npcs)
        target_npcs = set(target_state.active_npcs)
        
        # 检查移除的NPC
        removed_npcs = current_npcs - target_npcs
        if removed_npcs:
            conflicts.append({
                'type': 'npc_removed',
                'severity': 'info',
                'description': f'目标状态中不包含以下NPC: {", ".join(removed_npcs)}',
                'npcs': list(removed_npcs)
            })
        
        # 检查新增的NPC
        added_npcs = target_npcs - current_npcs
        if added_npcs:
            conflicts.append({
                'type': 'npc_added',
                'severity': 'info',
                'description': f'目标状态中包含以下新NPC: {", ".join(added_npcs)}',
                'npcs': list(added_npcs)
            })
        
        # 检查NPC状态变化
        common_npcs = current_npcs & target_npcs
        for npc_id in common_npcs:
            if npc_id in current_state.npc_states and npc_id in target_state.npc_states:
                current_npc = current_state.npc_states[npc_id]
                target_npc = target_state.npc_states[npc_id]
                
                # 检查情绪状态变化
                if current_npc.emotions != target_npc.emotions:
                    conflicts.append({
                        'type': 'npc_emotion_changed',
                        'severity': 'info',
                        'description': f'NPC {npc_id} 的情绪状态发生变化',
                        'npc_id': npc_id,
                        'current_emotions': current_npc.emotions,
                        'target_emotions': target_npc.emotions
                    })
                
                # 检查性格变化
                if current_npc.personality != target_npc.personality:
                    conflicts.append({
                        'type': 'npc_personality_changed',
                        'severity': 'warning',
                        'description': f'NPC {npc_id} 的性格发生变化',
                        'npc_id': npc_id,
                        'current_personality': current_npc.personality,
                        'target_personality': target_npc.personality
                    })
        
        return conflicts
    
    async def _detect_scene_conflict(
        self,
        current_state: SessionState,
        target_state: SessionState
    ) -> bool:
        """
        检测场景冲突
        
        Args:
            current_state: 当前会话状态
            target_state: 目标会话状态
            
        Returns:
            是否存在场景冲突
        """
        return current_state.current_scene_id != target_state.current_scene_id
    
    async def _detect_style_conflict(
        self,
        current_state: SessionState,
        target_state: SessionState
    ) -> bool:
        """
        检测DM风格冲突
        
        Args:
            current_state: 当前会话状态
            target_state: 目标会话状态
            
        Returns:
            是否存在风格冲突
        """
        return (
            current_state.dm_style != target_state.dm_style or
            current_state.narrative_tone != target_state.narrative_tone or
            current_state.combat_detail != target_state.combat_detail
        )
    
    async def assess_conflict_severity(
        self,
        conflicts: List[Dict[str, Any]]
    ) -> str:
        """
        评估冲突严重程度
        
        Args:
            conflicts: 冲突列表
            
        Returns:
            严重程度：'low', 'medium', 'high'
        """
        if not conflicts:
            return 'low'
        
        # 统计各严重程度的冲突数量
        severity_counts = {'critical': 0, 'warning': 0, 'info': 0}
        for conflict in conflicts:
            severity = conflict.get('severity', 'info')
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        # 评估总体严重程度
        if severity_counts['critical'] > 0:
            return 'high'
        elif severity_counts['warning'] >= 3:
            return 'high'
        elif severity_counts['warning'] >= 1:
            return 'medium'
        elif severity_counts['info'] >= 5:
            return 'medium'
        else:
            return 'low'