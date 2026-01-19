"""
时间管理器
管理游戏时间的推进和时间相关事件
"""

import abc
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable

from ...models.dm_models import (
    DispatchedTask,
    GameEvent,
    EventRule,
    EventTriggerType
)
from ...data_storage.interfaces import IGameRecordRepository
from ...core.logging import app_logger


class EventRuleBase(abc.ABC):
    """事件规则基类"""
    
    def __init__(
        self,
        rule_id: str,
        name: str,
        trigger_type: EventTriggerType,
        priority: int = 0
    ):
        """
        初始化事件规则
        
        Args:
            rule_id: 规则ID
            name: 规则名称
            trigger_type: 触发类型
            priority: 优先级
        """
        self.rule_id = rule_id
        self.name = name
        self.trigger_type = trigger_type
        self.priority = priority
        self.enabled = True
        self.logger = app_logger
    
    @abc.abstractmethod
    async def should_trigger(
        self,
        session_id: str,
        current_time: datetime,
        time_delta: timedelta
    ) -> bool:
        """
        判断是否应该触发
        
        Args:
            session_id: 会话ID
            current_time: 当前时间
            time_delta: 时间增量
            
        Returns:
            bool: 是否应该触发
        """
        pass
    
    @abc.abstractmethod
    async def execute(self, session_id: str) -> GameEvent:
        """
        执行事件
        
        Args:
            session_id: 会话ID
            
        Returns:
            GameEvent: 游戏事件
        """
        pass


class SpellSlotRecoveryEvent(EventRuleBase):
    """法术位恢复事件"""
    
    def __init__(
        self,
        rule_id: str,
        recovery_interval: timedelta = timedelta(hours=8),
        recovery_percentage: float = 1.0
    ):
        """
        初始化法术位恢复事件
        
        Args:
            rule_id: 规则ID
            recovery_interval: 恢复间隔
            recovery_percentage: 恢复百分比（0.0-1.0）
        """
        super().__init__(
            rule_id=rule_id,
            name="法术位恢复",
            trigger_type=EventTriggerType.TIME_BASED,
            priority=10
        )
        self.recovery_interval = recovery_interval
        self.recovery_percentage = recovery_percentage
        self.last_recovery_time: Dict[str, datetime] = {}
    
    async def should_trigger(
        self,
        session_id: str,
        current_time: datetime,
        time_delta: timedelta
    ) -> bool:
        """判断是否应该触发"""
        if not self.enabled:
            return False
        
        last_recovery = self.last_recovery_time.get(session_id)
        
        # 如果从未恢复过，检查是否到达恢复时间
        if last_recovery is None:
            return True
        
        # 检查是否经过足够的恢复时间
        time_since_last = current_time - last_recovery
        return time_since_last >= self.recovery_interval
    
    async def execute(self, session_id: str) -> GameEvent:
        """执行事件"""
        # 更新最后恢复时间
        self.last_recovery_time[session_id] = datetime.now()
        
        return GameEvent(
            event_id=f"spell_recovery_{session_id}",
            event_type="spell_slot_recovery",
            description=f"法术位恢复了{self.recovery_percentage * 100}%",
            effects={
                'recovery_percentage': self.recovery_percentage,
                'recovery_interval_hours': self.recovery_interval.total_seconds() / 3600
            }
        )


class HolidayEvent(EventRuleBase):
    """节日事件"""
    
    def __init__(
        self,
        rule_id: str,
        holiday_date: datetime,
        event_data: Dict[str, Any]
    ):
        """
        初始化节日事件
        
        Args:
            rule_id: 规则ID
            holiday_date: 节日日期
            event_data: 事件数据
        """
        super().__init__(
            rule_id=rule_id,
            name=f"节日-{holiday_date.strftime('%Y-%m-%d')}",
            trigger_type=EventTriggerType.TIME_BASED,
            priority=20
        )
        self.holiday_date = holiday_date.date()
        self.event_data = event_data
        self.triggered_sessions = set()
    
    async def should_trigger(
        self,
        session_id: str,
        current_time: datetime,
        time_delta: timedelta
    ) -> bool:
        """判断是否应该触发"""
        if not self.enabled:
            return False
        
        # 检查是否已触发
        if session_id in self.triggered_sessions:
            return False
        
        # 检查是否到达节日
        return current_time.date() == self.holiday_date
    
    async def execute(self, session_id: str) -> GameEvent:
        """执行事件"""
        # 标记为已触发
        self.triggered_sessions.add(session_id)
        
        return GameEvent(
            event_id=f"holiday_{self.holiday_date}",
            event_type="holiday",
            description=self.event_data.get('description', ''),
            effects=self.event_data.get('effects', {})
        )


class CustomEventRule(EventRuleBase):
    """自定义事件规则"""
    
    def __init__(
        self,
        rule_id: str,
        name: str,
        trigger_condition: Callable,
        event_handler: Callable,
        trigger_type: EventTriggerType = EventTriggerType.CONDITION_BASED,
        priority: int = 0
    ):
        """
        初始化自定义事件规则
        
        Args:
            rule_id: 规则ID
            name: 规则名称
            trigger_condition: 触发条件函数
            event_handler: 事件处理函数
            trigger_type: 触发类型
            priority: 优先级
        """
        super().__init__(
            rule_id=rule_id,
            name=name,
            trigger_type=trigger_type,
            priority=priority
        )
        self.trigger_condition = trigger_condition
        self.event_handler = event_handler
    
    async def should_trigger(
        self,
        session_id: str,
        current_time: datetime,
        time_delta: timedelta
    ) -> bool:
        """判断是否应该触发"""
        if not self.enabled:
            return False
        
        try:
            return await self.trigger_condition(session_id, current_time, time_delta)
        except Exception as e:
            self.logger.error(f"自定义事件触发条件检查失败: {e}")
            return False
    
    async def execute(self, session_id: str) -> GameEvent:
        """执行事件"""
        try:
            return await self.event_handler(session_id)
        except Exception as e:
            self.logger.error(f"自定义事件执行失败: {e}")
            return GameEvent(
                event_id=f"custom_error_{session_id}",
                event_type="error",
                description=f"事件执行失败: {str(e)}",
                effects={}
            )


class TimeManager:
    """时间管理器"""
    
    def __init__(
        self,
        game_record_repository: IGameRecordRepository
    ):
        """
        初始化时间管理器
        
        Args:
            game_record_repository: 游戏记录仓库
        """
        self.game_record_repository = game_record_repository
        self.event_rules: List[EventRuleBase] = []
        self.session_times: Dict[str, datetime] = {}  # session_id -> current_time
        self.logger = app_logger
    
    def register_event_rule(self, rule: EventRuleBase) -> None:
        """
        注册事件规则
        
        Args:
            rule: 事件规则
        """
        self.event_rules.append(rule)
        # 按优先级排序
        self.event_rules.sort(key=lambda r: r.priority, reverse=True)
        
        self.logger.info(f"注册事件规则: {rule.name} (优先级: {rule.priority})")
    
    def unregister_event_rule(self, rule_id: str) -> None:
        """
        注销事件规则
        
        Args:
            rule_id: 规则ID
        """
        self.event_rules = [
            rule for rule in self.event_rules
            if rule.rule_id != rule_id
        ]
        
        self.logger.info(f"注销事件规则: {rule_id}")
    
    def enable_event_rule(self, rule_id: str) -> bool:
        """
        启用事件规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            bool: 是否成功
        """
        for rule in self.event_rules:
            if rule.rule_id == rule_id:
                rule.enabled = True
                self.logger.info(f"启用事件规则: {rule.name}")
                return True
        return False
    
    def disable_event_rule(self, rule_id: str) -> bool:
        """
        禁用事件规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            bool: 是否成功
        """
        for rule in self.event_rules:
            if rule.rule_id == rule_id:
                rule.enabled = False
                self.logger.info(f"禁用事件规则: {rule.name}")
                return True
        return False
    
    async def calculate_time_cost(
        self,
        task: DispatchedTask
    ) -> timedelta:
        """
        计算任务的时间消耗
        
        Args:
            task: 分发的任务
            
        Returns:
            timedelta: 时间消耗
        """
        # 使用处理器计算的时间消耗
        if hasattr(task, 'time_cost'):
            return task.time_cost
        
        # 默认时间消耗
        return timedelta(minutes=1)
    
    async def advance_time(
        self,
        session_id: str,
        delta: timedelta
    ) -> None:
        """
        推进游戏时间
        
        Args:
            session_id: 会话ID
            delta: 时间增量
        """
        # 获取当前时间
        current_time = self.session_times.get(session_id)
        if current_time is None:
            current_time = datetime.now()
            self.session_times[session_id] = current_time
        
        # 推进时间
        new_time = current_time + delta
        self.session_times[session_id] = new_time
        
        # 保存时间记录
        await self._save_time_record(session_id, delta, current_time, new_time)
        
        self.logger.info(
            f"推进时间: {session_id} +{delta.total_seconds()}秒"
        )
    
    async def check_events(
        self,
        session_id: str,
        time_delta: timedelta
    ) -> List[GameEvent]:
        """
        检查并触发时间相关事件
        
        Args:
            session_id: 会话ID
            time_delta: 时间增量
            
        Returns:
            List[GameEvent]: 触发的事件列表
        """
        current_time = self.session_times.get(session_id)
        if current_time is None:
            current_time = datetime.now()
            self.session_times[session_id] = current_time
        
        triggered_events = []
        
        for rule in self.event_rules:
            try:
                # 检查是否应该触发
                if await rule.should_trigger(session_id, current_time, time_delta):
                    # 执行事件
                    event = await rule.execute(session_id)
                    triggered_events.append(event)
                    
                    self.logger.info(
                        f"触发事件: {rule.name} -> {event.event_type}"
                    )
            except Exception as e:
                self.logger.error(
                    f"事件规则执行失败: {rule.name} - {e}",
                    exc_info=True
                )
        
        return triggered_events
    
    async def get_current_time(self, session_id: str) -> datetime:
        """
        获取会话的当前时间
        
        Args:
            session_id: 会话ID
            
        Returns:
            datetime: 当前时间
        """
        return self.session_times.get(session_id, datetime.now())
    
    async def set_current_time(
        self,
        session_id: str,
        new_time: datetime
    ) -> None:
        """
        设置会话的当前时间
        
        Args:
            session_id: 会话ID
            new_time: 新时间
        """
        self.session_times[session_id] = new_time
        self.logger.info(f"设置时间: {session_id} -> {new_time}")
    
    async def reset_session_time(self, session_id: str) -> None:
        """
        重置会话时间
        
        Args:
            session_id: 会话ID
        """
        if session_id in self.session_times:
            del self.session_times[session_id]
        
        # 重置相关事件规则的状态
        for rule in self.event_rules:
            if hasattr(rule, 'triggered_sessions'):
                rule.triggered_sessions.discard(session_id)
            if hasattr(rule, 'last_recovery_time'):
                rule.last_recovery_time.pop(session_id, None)
        
        self.logger.info(f"重置会话时间: {session_id}")
    
    async def cleanup_session(self, session_id: str) -> None:
        """
        清理会话
        
        Args:
            session_id: 会话ID
        """
        if session_id in self.session_times:
            del self.session_times[session_id]
        
        self.logger.info(f"清理会话: {session_id}")
    
    async def _save_time_record(
        self,
        session_id: str,
        delta: timedelta,
        old_time: datetime,
        new_time: datetime
    ) -> None:
        """
        保存时间记录
        
        Args:
            session_id: 会话ID
            delta: 时间增量
            old_time: 旧时间
            new_time: 新时间
        """
        # TODO: 实现时间记录保存到数据库
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取时间管理器状态
        
        Returns:
            Dict: 状态信息
        """
        return {
            'active_sessions': len(self.session_times),
            'event_rules_count': len(self.event_rules),
            'enabled_event_rules': len([r for r in self.event_rules if r.enabled]),
            'session_times': {
                session_id: time.isoformat()
                for session_id, time in self.session_times.items()
            }
        }


# ==================== 工厂函数 ====================

def create_time_manager(
    game_record_repository: IGameRecordRepository
) -> TimeManager:
    """
    创建时间管理器实例
    
    Args:
        game_record_repository: 游戏记录仓库
        
    Returns:
        TimeManager: 时间管理器实例
    """
    return TimeManager(
        game_record_repository=game_record_repository
    )


def create_spell_recovery_event(
    rule_id: str = "spell_recovery_default",
    recovery_interval: timedelta = timedelta(hours=8),
    recovery_percentage: float = 1.0
) -> SpellSlotRecoveryEvent:
    """
    创建法术位恢复事件
    
    Args:
        rule_id: 规则ID
        recovery_interval: 恢复间隔
        recovery_percentage: 恢复百分比
        
    Returns:
        SpellSlotRecoveryEvent: 法术位恢复事件
    """
    return SpellSlotRecoveryEvent(
        rule_id=rule_id,
        recovery_interval=recovery_interval,
        recovery_percentage=recovery_percentage
    )


def create_holiday_event(
    rule_id: str,
    holiday_date: datetime,
    event_data: Dict[str, Any]
) -> HolidayEvent:
    """
    创建节日事件
    
    Args:
        rule_id: 规则ID
        holiday_date: 节日日期
        event_data: 事件数据
        
    Returns:
        HolidayEvent: 节日事件
    """
    return HolidayEvent(
        rule_id=rule_id,
        holiday_date=holiday_date,
        event_data=event_data
    )


def create_custom_event_rule(
    rule_id: str,
    name: str,
    trigger_condition: Callable,
    event_handler: Callable,
    trigger_type: EventTriggerType = EventTriggerType.CONDITION_BASED,
    priority: int = 0
) -> CustomEventRule:
    """
    创建自定义事件规则
    
    Args:
        rule_id: 规则ID
        name: 规则名称
        trigger_condition: 触发条件函数
        event_handler: 事件处理函数
        trigger_type: 触发类型
        priority: 优先级
        
    Returns:
        CustomEventRule: 自定义事件规则
    """
    return CustomEventRule(
        rule_id=rule_id,
        name=name,
        trigger_condition=trigger_condition,
        event_handler=event_handler,
        trigger_type=trigger_type,
        priority=priority
    )