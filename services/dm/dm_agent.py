"""
DM智能体
DM核心智能体服务，协调所有组件处理玩家输入并生成响应
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from ...models.dm_models import (
    DMConfig,
    PlayerInput,
    ClassifiedInput,
    ExtractedEntity,
    DispatchedTask,
    GameSession,
    DMResponse,
    PerceptibleInfo,
    GameEvent,
    NPCResponse,
    DMStyle,
    CustomDMStyleRequest
)
from ...agent_orchestration.core import BaseAgent, AgentConfig, ExecutionContext, ReasoningMode
from ...model_adapter import ModelScheduler
from ...data_storage.interfaces import IEntityRepository, IGameRecordRepository
from ...agent_orchestration.interfaces import IOrchestrator

from .input_classifier import InputClassifier, create_input_classifier
from .entity_extractor import EntityExtractor, create_entity_extractor
from .task_dispatcher import TaskDispatcher, create_task_dispatcher
from .npc_pool import NPCAgentPool, create_npc_pool
from .time_manager import TimeManager, create_time_manager, create_spell_recovery_event
from .response_generator import ResponseGenerator, create_response_generator
from ...core.logging import app_logger


class DMAgent(BaseAgent):
    """DM智能体实现"""
    
    def __init__(
        self,
        agent_id: str,
        config: DMConfig,
        model_scheduler: ModelScheduler,
        entity_repository: IEntityRepository,
        game_record_repository: IGameRecordRepository,
        orchestrator: Optional[IOrchestrator] = None,
        **kwargs
    ):
        """
        初始化DM智能体
        
        Args:
            agent_id: 智能体ID
            config: DM配置
            model_scheduler: 模型调度器
            entity_repository: 实体仓库
            game_record_repository: 游戏记录仓库
            orchestrator: 编排器（可选）
        """
        # 转换DMConfig为AgentConfig
        agent_config = AgentConfig(
            agent_id=agent_id,
            agent_type="dm",
            version="1.0.0",
            reasoning_mode=ReasoningMode.COT,
            reasoning_config={},
            enabled_tools=config.enabled_tools,
            tool_config=config.tool_config,
            max_execution_time=config.max_execution_time,
            max_memory_usage=config.max_memory_usage,
            concurrency_limit=config.concurrency_limit,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            system_prompt=config.get_effective_system_prompt(),
            personality=config.personality,
            behavior_patterns=config.behavior_patterns
        )
        
        # 初始化基类
        super().__init__(
            agent_id=agent_id,
            config=agent_config,
            model_scheduler=model_scheduler,
            orchestrator=orchestrator,
            **kwargs
        )
        
        self.config = config
        self.entity_repository = entity_repository
        self.game_record_repository = game_record_repository
        
        # 核心组件
        self.input_classifier: InputClassifier = None
        self.entity_extractor: EntityExtractor = None
        self.task_dispatcher: TaskDispatcher = None
        self.npc_pool: NPCAgentPool = None
        self.time_manager: TimeManager = None
        self.response_generator: ResponseGenerator = None
        
        # 会话状态
        self.current_session: Optional[GameSession] = None
        self.pending_npc_responses: Dict[str, NPCResponse] = {}
        
        # 自定义DM风格缓存
        self.custom_dm_styles: Dict[str, CustomDMStyleRequest] = {}
        
        self.logger = app_logger
    
    async def initialize_components(self) -> None:
        """初始化所有组件"""
        try:
            # 初始化输入分类器
            self.input_classifier = create_input_classifier(
                model_scheduler=self.model_scheduler,
                temperature=0.3
            )
            
            # 初始化实体抽取器
            self.entity_extractor = create_entity_extractor(
                model_scheduler=self.model_scheduler,
                entity_repository=self.entity_repository
            )
            
            # 初始化任务分发器
            self.task_dispatcher = create_task_dispatcher()
            
            # 初始化NPC智能体池
            self.npc_pool = create_npc_pool(
                entity_repository=self.entity_repository,
                model_scheduler=self.model_scheduler
            )
            
            # 初始化时间管理器
            self.time_manager = create_time_manager(
                game_record_repository=self.game_record_repository
            )
            
            # 注册默认事件规则
            await self._register_default_event_rules()
            
            # 初始化响应生成器
            self.response_generator = create_response_generator(
                model_scheduler=self.model_scheduler,
                dm_style=self.config.dm_style,
                narrative_tone=self.config.narrative_tone,
                combat_detail=self.config.combat_detail
            )
            
            self.logger.info("DM智能体组件初始化完成")
            
        except Exception as e:
            self.logger.error(f"DM组件初始化失败: {e}", exc_info=True)
            raise
    
    async def _register_default_event_rules(self) -> None:
        """注册默认事件规则"""
        # 注册法术位恢复事件
        spell_recovery = create_spell_recovery_event(
            rule_id="spell_recovery_default",
            recovery_interval=timedelta(hours=8),
            recovery_percentage=1.0
        )
        self.time_manager.register_event_rule(spell_recovery)
    
    async def initialize_session(
        self,
        session_id: str,
        dm_id: str,
        name: str,
        description: str,
        campaign_id: Optional[str] = None,
        npc_ids: Optional[List[str]] = None
    ) -> GameSession:
        """
        初始化游戏会话
        
        Args:
            session_id: 会话ID
            dm_id: DM ID
            name: 会话名称
            description: 会话描述
            campaign_id: 战役ID（可选）
            npc_ids: NPC ID列表（可选）
            
        Returns:
            GameSession: 游戏会话
        """
        # 创建会话对象
        now = datetime.now()
        session = GameSession(
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
            updated_at=now,
            dm_style=self.config.dm_style,
            narrative_tone=self.config.narrative_tone,
            combat_detail=self.config.combat_detail,
            custom_dm_style=None,
            custom_system_prompt=None
        )
        
        # 设置当前会话
        self.current_session = session
        
        # 初始化NPC到会话
        if npc_ids:
            await self.npc_pool.batch_initialize_npcs(npc_ids, session_id)
        
        # 保存会话到数据库
        # TODO: 实现会话保存
        
        self.logger.info(f"初始化游戏会话: {session_id}")
        
        return session
    
    async def process_player_turn(
        self,
        session_id: str,
        player_inputs: List[PlayerInput],
        context: Optional[ExecutionContext] = None
    ) -> DMResponse:
        """
        处理玩家回合
        
        Args:
            session_id: 会话ID
            player_inputs: 玩家输入列表
            context: 执行上下文（可选）
            
        Returns:
            DMResponse: DM响应
        """
        try:
            # 设置当前会话
            if not self.current_session or self.current_session.session_id != session_id:
                # 加载会话
                # TODO: 从数据库加载会话
                pass
            
            start_time = datetime.now()
            self.logger.info(
                f"开始处理玩家回合: {session_id} - "
                f"{len(player_inputs)} 个输入"
            )
            
            # 1. 分类输入
            classified_inputs = await self._classify_inputs(player_inputs)
            
            # 2. 抽取实体
            entities = await self._extract_entities(classified_inputs)
            
            # 3. 分发任务
            tasks = await self._dispatch_tasks(classified_inputs, entities)
            
            # 4. 处理NPC交互
            npc_results = await self._handle_npc_interactions(session_id, tasks)
            
            # 5. 推进时间
            time_delta = await self._advance_time(tasks)
            
            # 6. 触发事件
            events = await self._trigger_events(session_id, time_delta)
            
            # 7. 更新记忆
            await self._update_memories(session_id, player_inputs, tasks, npc_results, events)
            
            # 8. 收集可感知信息
            perceptible_info = await self._collect_perceptible_info(
                player_inputs, tasks, npc_results, events
            )
            
            # 9. 生成响应
            response = await self._generate_response(
                perceptible_info, context
            )
            
            # 记录处理时间
            processing_time = (datetime.now() - start_time).total_seconds()
            self.logger.info(
                f"玩家回合处理完成: {processing_time:.2f}秒"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"玩家回合处理失败: {e}", exc_info=True)
            # 返回错误响应
            return await self._generate_error_response(str(e))
    
    async def _classify_inputs(
        self,
        inputs: List[PlayerInput]
    ) -> List[ClassifiedInput]:
        """
        分类玩家输入
        
        Args:
            inputs: 玩家输入列表
            
        Returns:
            List[ClassifiedInput]: 分类结果列表
        """
        return await self.input_classifier.batch_classify(inputs)
    
    async def _extract_entities(
        self,
        classified_inputs: List[ClassifiedInput]
    ) -> List[ExtractedEntity]:
        """
        抽取实体
        
        Args:
            classified_inputs: 分类后的输入列表
            
        Returns:
            List[ExtractedEntity]: 抽取的实体列表
        """
        import asyncio
        
        tasks = [
            self.entity_extractor.extract(classified_input)
            for classified_input in classified_inputs
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 过滤异常
        extracted_entities = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(
                    f"第{i}个输入实体抽取失败: {result}"
                )
                # 返回空实体
                extracted_entities.append(ExtractedEntity(
                    original_input=classified_inputs[i],
                    entities=[]
                ))
            else:
                extracted_entities.append(result)
        
        return extracted_entities
    
    async def _dispatch_tasks(
        self,
        classified_inputs: List[ClassifiedInput],
        entities_list: List[ExtractedEntity]
    ) -> List[DispatchedTask]:
        """
        分发任务
        
        Args:
            classified_inputs: 分类后的输入列表
            entities_list: 抽取的实体列表
            
        Returns:
            List[DispatchedTask]: 分发的任务列表
        """
        return await self.task_dispatcher.batch_dispatch(
            classified_inputs, entities_list
        )
    
    async def _handle_npc_interactions(
        self,
        session_id: str,
        tasks: List[DispatchedTask]
    ) -> Dict[str, NPCResponse]:
        """
        处理NPC交互
        
        Args:
            session_id: 会话ID
            tasks: 分发的任务列表
            
        Returns:
            Dict[str, NPCResponse]: NPC响应字典
        """
        return await self.npc_pool.process_npc_interactions(session_id, tasks)
    
    async def _advance_time(
        self,
        tasks: List[DispatchedTask]
    ) -> timedelta:
        """
        推进游戏时间
        
        Args:
            tasks: 分发的任务列表
            
        Returns:
            timedelta: 时间增量
        """
        total_time = timedelta()
        
        for task in tasks:
            time_cost = await self.time_manager.calculate_time_cost(task)
            total_time += time_cost
        
        if self.current_session:
            await self.time_manager.advance_time(
                self.current_session.session_id,
                total_time
            )
        
        return total_time
    
    async def _trigger_events(
        self,
        session_id: str,
        time_delta: timedelta
    ) -> List[GameEvent]:
        """
        触发时间相关事件
        
        Args:
            session_id: 会话ID
            time_delta: 时间增量
            
        Returns:
            List[GameEvent]: 触发的事件列表
        """
        return await self.time_manager.check_events(session_id, time_delta)
    
    async def _update_memories(
        self,
        session_id: str,
        inputs: List[PlayerInput],
        tasks: List[DispatchedTask],
        npc_results: Dict[str, NPCResponse],
        events: List[GameEvent]
    ) -> None:
        """
        更新各种记忆
        
        Args:
            session_id: 会话ID
            inputs: 玩家输入列表
            tasks: 分发的任务列表
            npc_results: NPC响应字典
            events: 事件列表
        """
        # 更新NPC记忆
        await self.npc_pool.update_npc_memories(
            session_id, tasks, npc_results
        )
        
        # 保存游戏记录
        # TODO: 实现游戏记录保存
        
        # TODO: 实现场景记忆更新
        # TODO: 实现历史记忆更新
    
    async def _collect_perceptible_info(
        self,
        inputs: List[PlayerInput],
        tasks: List[DispatchedTask],
        npc_results: Dict[str, NPCResponse],
        events: List[GameEvent]
    ) -> PerceptibleInfo:
        """
        收集玩家角色能感知到的信息
        
        Args:
            inputs: 玩家输入列表
            tasks: 分发的任务列表
            npc_results: NPC响应字典
            events: 事件列表
            
        Returns:
            PerceptibleInfo: 可感知信息
        """
        # 收集玩家行动
        player_actions = [input_data.content for input_data in inputs]
        
        # 收集NPC响应
        npc_responses = npc_results
        
        # 收集事件
        game_events = events
        
        # 构建场景描述
        scene_description = await self._build_scene_description(tasks, npc_results)
        
        # 收集变化的实体
        changed_entities = []
        for task in tasks:
            if task.entities:
                changed_entities.extend(task.entities.entities)
        
        return PerceptibleInfo(
            player_actions=player_actions,
            npc_responses=npc_responses,
            events=game_events,
            scene_description=scene_description,
            changed_entities=changed_entities
        )
    
    async def _build_scene_description(
        self,
        tasks: List[DispatchedTask],
        npc_responses: Dict[str, NPCResponse]
    ) -> str:
        """
        构建场景描述
        
        Args:
            tasks: 分发的任务列表
            npc_responses: NPC响应字典
            
        Returns:
            str: 场景描述
        """
        # TODO: 实现场景描述生成
        if self.current_session and self.current_session.current_scene_id:
            # 从数据库加载场景
            # TODO: 实现场景加载
            return f"场景 {self.current_session.current_scene_id}"
        return "当前场景"
    
    async def _generate_response(
        self,
        perceptible_info: PerceptibleInfo,
        context: Optional[ExecutionContext] = None
    ) -> DMResponse:
        """
        生成DM响应
        
        Args:
            perceptible_info: 可感知信息
            context: 执行上下文（可选）
            
        Returns:
            DMResponse: DM响应
        """
        return await self.response_generator.generate(
            perceptible_info=perceptible_info,
            context=context.metadata if context else None
        )
    
    async def _generate_error_response(
        self,
        error_message: str
    ) -> DMResponse:
        """
        生成错误响应
        
        Args:
            error_message: 错误消息
            
        Returns:
            DMResponse: DM响应
        """
        return await self.response_generator.generate_error_response(error_message)
    
    async def update_dm_style(
        self,
        dm_style: Optional[str] = None,
        narrative_tone: Optional[str] = None,
        combat_detail: Optional[str] = None,
        custom_style_name: Optional[str] = None,
        custom_system_prompt: Optional[str] = None
    ) -> None:
        """
        更新DM风格（支持自定义风格）
        
        Args:
            dm_style: DM风格（可选）
            narrative_tone: 叙述基调（可选）
            combat_detail: 战斗细节（可选）
            custom_style_name: 自定义风格名称（可选）
            custom_system_prompt: 自定义系统提示词（可选）
        """
        from ...models.dm_models import DMStyle, NarrativeTone, CombatDetail
        
        if custom_style_name:
            # 使用自定义风格
            if custom_style_name in self.custom_dm_styles:
                custom_style_request = self.custom_dm_styles[custom_style_name]
                # 更新响应生成器以使用自定义风格
                from .response_generator import create_custom_response_generator
                new_generator = create_custom_response_generator(
                    model_scheduler=self.model_scheduler,
                    custom_style_request=custom_style_request
                )
                self.response_generator = new_generator
            else:
                # 预定义风格名称无效
                self.logger.warning(
                    f"未找到自定义风格: {custom_style_name}，"
                    "使用默认风格"
                )
        else:
            # 使用预定义风格
            if dm_style:
                self.config.dm_style = DMStyle(dm_style)
            if narrative_tone:
                self.config.narrative_tone = NarrativeTone(narrative_tone)
            if combat_detail:
                self.config.combat_detail = CombatDetail(combat_detail)
            
            # 更新响应生成器风格
            self.response_generator.update_style(
                dm_style=self.config.dm_style,
                narrative_tone=self.config.narrative_tone,
                combat_detail=self.config.combat_detail,
                custom_style_request=None
            )
        
        # 更新会话配置
        if self.current_session:
            self.current_session.dm_style = self.config.dm_style.value
            self.current_session.narrative_tone = self.config.narrative_tone.value
            self.current_session.combat_detail = self.config.combat_detail.value
            
            # 如果使用自定义风格，更新会话配置
            if custom_style_name:
                self.current_session.custom_dm_style = custom_style_name
                if custom_system_prompt:
                    self.current_session.custom_system_prompt = custom_system_prompt
        
        self.logger.info(
            f"更新DM风格: {self.config.dm_style.value}"
        )
    
    async def register_custom_dm_style(
        self,
        style_name: str,
        style_request: CustomDMStyleRequest
    ) -> None:
        """
        注册自定义DM风格
        
        Args:
            style_name: 风格名称
            style_request: 自定义风格请求
        """
        self.custom_dm_styles[style_name] = style_request
        self.logger.info(f"注册自定义DM风格: {style_name}")
    
    async def get_custom_dm_styles(self) -> Dict[str, CustomDMStyleRequest]:
        """
        获取所有自定义DM风格
        
        Returns:
            Dict: 自定义DM风格字典
        """
        return self.custom_dm_styles
    
    async def remove_custom_dm_style(self, style_name: str) -> bool:
        """
        删除自定义DM风格
        
        Args:
            style_name: 风格名称
            
        Returns:
            bool: 是否成功
        """
        if style_name in self.custom_dm_styles:
            del self.custom_dm_styles[style_name]
            self.logger.info(f"删除自定义DM风格: {style_name}")
            return True
        return False
    
    async def cleanup_session(self, session_id: str) -> None:
        """
        清理会话
        
        Args:
            session_id: 会话ID
        """
        # 清理NPC智能体池
        await self.npc_pool.cleanup_session(session_id)
        
        # 重置时间管理器
        await self.time_manager.cleanup_session(session_id)
        
        # 如果是当前会话，清除
        if self.current_session and self.current_session.session_id == session_id:
            self.current_session = None
        
        self.logger.info(f"清理会话: {session_id}")
    
    async def shutdown(self) -> None:
        """关闭DM智能体"""
        # 关闭NPC智能体池
        await self.npc_pool.shutdown_all()
        
        # 关闭基类
        await super().shutdown()
        
        self.logger.info(f"DM智能体关闭: {self.agent_id}")
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            Dict: 会话状态信息
        """
        return {
            'session_id': session_id,
            'current_time': (await self.time_manager.get_current_time(session_id)).isoformat(),
            'active_npcs': (await self.npc_pool.get_session_npcs(session_id)),
            'npc_pool_status': self.npc_pool.get_pool_status(),
            'time_manager_status': self.time_manager.get_status(),
            'dm_style': self.config.dm_style.value,
            'narrative_tone': self.config.narrative_tone.value,
            'combat_detail': self.config.combat_detail.value,
            'custom_dm_style': self.current_session.custom_dm_style if self.current_session else None
        }


# ==================== 工厂函数 ====================

async def create_dm_agent(
    agent_id: str,
    config: DMConfig,
    model_scheduler: ModelScheduler,
    entity_repository: IEntityRepository,
    game_record_repository: IGameRecordRepository,
    orchestrator: Optional[IOrchestrator] = None
) -> DMAgent:
    """
    创建DM智能体实例
    
    Args:
        agent_id: 智能体ID
        config: DM配置
        model_scheduler: 模型调度器
        entity_repository: 实体仓库
        game_record_repository: 游戏记录仓库
        orchestrator: 编排器（可选）
        
    Returns:
        DMAgent: DM智能体实例
    """
    # 创建DM智能体
    dm_agent = DMAgent(
        agent_id=agent_id,
        config=config,
        model_scheduler=model_scheduler,
        entity_repository=entity_repository,
        game_record_repository=game_record_repository,
        orchestrator=orchestrator
    )
    
    # 初始化智能体
    await dm_agent.initialize()
    
    # 初始化组件
    await dm_agent.initialize_components()
    
    return dm_agent