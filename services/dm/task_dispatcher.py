"""
任务分发器和处理器
将任务分发给对应的处理模块
"""

import abc
import logging
import uuid
from datetime import timedelta
from typing import Dict, List, Optional, Any

from ...models.dm_models import (
    ClassifiedInput,
    ExtractedEntity,
    DispatchedTask,
    InputType,
    TaskData,
    ActionTaskData,
    DialogueTaskData,
    ThoughtTaskData,
    OCCTaskData,
    CommandTaskData
)
from ...core.logging import app_logger


class TaskProcessor(abc.ABC):
    """任务处理器基类"""
    
    def __init__(self):
        self.logger = app_logger
    
    @abc.abstractmethod
    async def process(
        self,
        classified_input: ClassifiedInput,
        entities: ExtractedEntity
    ) -> TaskData:
        """
        处理任务
        
        Args:
            classified_input: 分类后的输入
            entities: 抽取的实体
            
        Returns:
            TaskData: 任务数据
        """
        pass
    
    @abc.abstractmethod
    def requires_npc_response(
        self,
        classified_input: ClassifiedInput
    ) -> bool:
        """
        判断是否需要NPC响应
        
        Args:
            classified_input: 分类后的输入
            
        Returns:
            bool: 是否需要NPC响应
        """
        pass
    
    @abc.abstractmethod
    def get_target_npc(
        self,
        classified_input: ClassifiedInput
    ) -> Optional[str]:
        """
        获取目标NPC ID
        
        Args:
            classified_input: 分类后的输入
            
        Returns:
            Optional[str]: 目标NPC ID
        """
        pass
    
    @abc.abstractmethod
    async def calculate_time_cost(self, task_data: TaskData) -> timedelta:
        """
        计算时间消耗
        
        Args:
            task_data: 任务数据
            
        Returns:
            timedelta: 时间消耗
        """
        pass


class ActionProcessor(TaskProcessor):
    """动作处理器"""
    
    # 动作类型时间映射（单位：秒）
    ACTION_TIME_COST = {
        'cast_spell': 60,          # 施法
        'check': 10,               # 检定
        'attack': 5,               # 攻击
        'move': 30,                # 移动
        'interact': 15,            # 交互
        'search': 60,              # 搜索
        'rest': 3600,              # 休息
        'generic': 30               # 通用动作
    }
    
    async def process(
        self,
        classified_input: ClassifiedInput,
        entities: ExtractedEntity
    ) -> ActionTaskData:
        """
        处理动作
        
        Args:
            classified_input: 分类后的输入
            entities: 抽取的实体
            
        Returns:
            ActionTaskData: 动作任务数据
        """
        action_type = classified_input.action_type or 'generic'
        target = classified_input.target
        
        action_data = ActionTaskData(
            action_type=action_type,
            target=target,
            involved_entities=entities.entities
        )
        
        # 根据动作类型执行相应逻辑
        if action_type == 'cast_spell':
            await self._handle_spell_cast(action_data, entities)
        elif action_type == 'check':
            await self._handle_skill_check(action_data, entities)
        elif action_type == 'attack':
            await self._handle_attack(action_data, entities)
        else:
            await self._handle_generic_action(action_data, entities)
        
        self.logger.info(
            f"处理动作: {action_type} - "
            f"{classified_input.original_input.content[:50]}..."
        )
        
        return action_data
    
    def requires_npc_response(
        self,
        classified_input: ClassifiedInput
    ) -> bool:
        """判断是否需要NPC响应"""
        # 如果动作针对NPC，需要NPC响应
        if classified_input.target and classified_input.target.get('type') == 'NPC':
            return True
        return False
    
    def get_target_npc(
        self,
        classified_input: ClassifiedInput
    ) -> Optional[str]:
        """获取目标NPC ID"""
        if classified_input.target and classified_input.target.get('type') == 'NPC':
            return classified_input.target.get('id')
        return None
    
    async def calculate_time_cost(self, task_data: TaskData) -> timedelta:
        """计算时间消耗"""
        if isinstance(task_data, ActionTaskData):
            action_type = task_data.action_type
            seconds = self.ACTION_TIME_COST.get(
                action_type,
                self.ACTION_TIME_COST['generic']
            )
            return timedelta(seconds=seconds)
        return timedelta(minutes=1)
    
    async def _handle_spell_cast(
        self,
        action_data: ActionTaskData,
        entities: ExtractedEntity
    ) -> None:
        """
        处理施法
        
        Args:
            action_data: 动作数据
            entities: 抽取的实体
        """
        # 查找法术实体
        spell_entities = entities.get_entities_by_type('SPELL')
        if spell_entities:
            spell = spell_entities[0]
            action_data.result = {
                'spell': spell.extraction.name,
                'spell_id': spell.matched_entity.id if spell.matched_entity else None,
                'is_new': spell.is_new
            }
            self.logger.debug(f"识别法术: {spell.extraction.name}")
    
    async def _handle_skill_check(
        self,
        action_data: ActionTaskData,
        entities: ExtractedEntity
    ) -> None:
        """
        处理技能检定
        
        Args:
            action_data: 动作数据
            entities: 抽取的实体
        """
        # 查找技能实体
        skill_entities = entities.get_entities_by_type('SKILL')
        if skill_entities:
            skill = skill_entities[0]
            action_data.result = {
                'skill': skill.extraction.name,
                'skill_id': skill.matched_entity.id if skill.matched_entity else None,
                'is_new': skill.is_new
            }
            self.logger.debug(f"识别技能: {skill.extraction.name}")
    
    async def _handle_attack(
        self,
        action_data: ActionTaskData,
        entities: ExtractedEntity
    ) -> None:
        """
        处理攻击
        
        Args:
            action_data: 动作数据
            entities: 抽取的实体
        """
        # 查找目标实体
        if action_data.target:
            target_type = action_data.target.get('type')
            action_data.result = {
                'target_type': target_type,
                'target_name': action_data.target.get('name')
            }
            self.logger.debug(
                f"识别攻击目标: {target_type} - {action_data.target.get('name')}"
            )
    
    async def _handle_generic_action(
        self,
        action_data: ActionTaskData,
        entities: ExtractedEntity
    ) -> None:
        """
        处理通用动作
        
        Args:
            action_data: 动作数据
            entities: 抽取的实体
        """
        action_data.result = {
            'entities_involved': len(entities.entities)
        }


class DialogueProcessor(TaskProcessor):
    """对话处理器"""
    
    async def process(
        self,
        classified_input: ClassifiedInput,
        entities: ExtractedEntity
    ) -> DialogueTaskData:
        """
        处理对话
        
        Args:
            classified_input: 分类后的输入
            entities: 抽取的实体
            
        Returns:
            DialogueTaskData: 对话任务数据
        """
        dialogue_data = DialogueTaskData(
            speaker=classified_input.original_input.character_name,
            content=classified_input.original_input.content,
            target=classified_input.target
        )
        
        self.logger.info(
            f"处理对话: {dialogue_data.speaker} -> "
            f"{dialogue_data.target.get('name') if dialogue_data.target else 'None'}"
        )
        
        return dialogue_data
    
    def requires_npc_response(
        self,
        classified_input: ClassifiedInput
    ) -> bool:
        """判断是否需要NPC响应"""
        # 如果对话针对NPC，需要NPC响应
        if classified_input.target and classified_input.target.get('type') == 'NPC':
            return True
        return False
    
    def get_target_npc(
        self,
        classified_input: ClassifiedInput
    ) -> Optional[str]:
        """获取目标NPC ID"""
        if classified_input.target and classified_input.target.get('type') == 'NPC':
            return classified_input.target.get('id')
        return None
    
    async def calculate_time_cost(self, task_data: TaskData) -> timedelta:
        """计算时间消耗"""
        # 对话通常需要15秒
        return timedelta(seconds=15)


class ThoughtProcessor(TaskProcessor):
    """心理描述处理器"""
    
    async def process(
        self,
        classified_input: ClassifiedInput,
        entities: ExtractedEntity
    ) -> ThoughtTaskData:
        """
        处理心理描述
        
        Args:
            classified_input: 分类后的输入
            entities: 抽取的实体
            
        Returns:
            ThoughtTaskData: 心理描述任务数据
        """
        thought_data = ThoughtTaskData(
            character=classified_input.original_input.character_name,
            content=classified_input.original_input.content
        )
        
        self.logger.info(
            f"处理心理描述: {thought_data.character}"
        )
        
        return thought_data
    
    def requires_npc_response(
        self,
        classified_input: ClassifiedInput
    ) -> bool:
        """判断是否需要NPC响应"""
        return False
    
    def get_target_npc(
        self,
        classified_input: ClassifiedInput
    ) -> Optional[str]:
        """获取目标NPC ID"""
        return None
    
    async def calculate_time_cost(self, task_data: TaskData) -> timedelta:
        """计算时间消耗"""
        # 心理描述不消耗游戏时间
        return timedelta(seconds=0)


class OOCProcessor(TaskProcessor):
    """场外发言处理器"""
    
    async def process(
        self,
        classified_input: ClassifiedInput,
        entities: ExtractedEntity
    ) -> OCCTaskData:
        """
        处理场外发言
        
        Args:
            classified_input: 分类后的输入
            entities: 抽取的实体
            
        Returns:
            OCCTaskData: 场外发言任务数据
        """
        ooc_data = OCCTaskData(
            player=classified_input.original_input.character_name,
            content=classified_input.original_input.content
        )
        
        self.logger.info(
            f"处理场外发言: {ooc_data.player}"
        )
        
        return ooc_data
    
    def requires_npc_response(
        self,
        classified_input: ClassifiedInput
    ) -> bool:
        """判断是否需要NPC响应"""
        return False
    
    def get_target_npc(
        self,
        classified_input: ClassifiedInput
    ) -> Optional[str]:
        """获取目标NPC ID"""
        return None
    
    async def calculate_time_cost(self, task_data: TaskData) -> timedelta:
        """计算时间消耗"""
        # 场外发言不消耗游戏时间
        return timedelta(seconds=0)


class CommandProcessor(TaskProcessor):
    """指令处理器"""
    
    # 指令时间映射（单位：秒）
    COMMAND_TIME_COST = {
        '回合结束': 5,
        '/回合结束': 5,
        '/end_turn': 5,
        '/施法': 60,
        '/cast': 60,
        '/投骰子': 5,
        '/roll': 5,
        '/查询角色': 0,
        '/check_character': 0,
        '/查询物品': 0,
        '/check_item': 0,
        '/保存': 5,
        '/save': 5,
        'generic': 5
    }
    
    async def process(
        self,
        classified_input: ClassifiedInput,
        entities: ExtractedEntity
    ) -> CommandTaskData:
        """
        处理指令
        
        Args:
            classified_input: 分类后的输入
            entities: 抽取的实体
            
        Returns:
            CommandTaskData: 指令任务数据
        """
        command_text = classified_input.original_input.content
        command = classified_input.action_type or 'generic'
        arguments = command_text.split(maxsplit=1)[1:] if ' ' in command_text else []
        
        command_data = CommandTaskData(
            command=command,
            arguments=arguments,
            raw_input=command_text
        )
        
        # 智能解析指令
        parsed_data = await self._parse_command(command_data, entities)
        command_data.parsed_data = parsed_data
        
        self.logger.info(
            f"处理指令: {command} - 参数: {arguments}"
        )
        
        return command_data
    
    def requires_npc_response(
        self,
        classified_input: ClassifiedInput
    ) -> bool:
        """判断是否需要NPC响应"""
        return False
    
    def get_target_npc(
        self,
        classified_input: ClassifiedInput
    ) -> Optional[str]:
        """获取目标NPC ID"""
        return None
    
    async def calculate_time_cost(self, task_data: TaskData) -> timedelta:
        """计算时间消耗"""
        if isinstance(task_data, CommandTaskData):
            command = task_data.command
            seconds = self.COMMAND_TIME_COST.get(
                command,
                self.COMMAND_TIME_COST['generic']
            )
            return timedelta(seconds=seconds)
        return timedelta(seconds=5)
    
    async def _parse_command(
        self,
        command_data: CommandTaskData,
        entities: ExtractedEntity
    ) -> Dict[str, Any]:
        """
        智能解析指令
        
        Args:
            command_data: 指令数据
            entities: 抽取的实体
            
        Returns:
            Dict: 解析后的数据
        """
        command = command_data.command
        
        # 根据指令类型进行解析
        if command in ['/施法', '/cast']:
            return await self._parse_cast_command(command_data, entities)
        elif command in ['/投骰子', '/roll']:
            return await self._parse_roll_command(command_data)
        elif command in ['/查询角色', '/check_character']:
            return await self._parse_check_character_command(command_data)
        else:
            # 默认解析
            return {
                'command_type': command,
                'arguments': command_data.arguments,
                'has_parameters': len(command_data.arguments) > 0
            }
    
    async def _parse_cast_command(
        self,
        command_data: CommandTaskData,
        entities: ExtractedEntity
    ) -> Dict[str, Any]:
        """
        解析施法指令
        
        Args:
            command_data: 指令数据
            entities: 抽取的实体
            
        Returns:
            Dict: 解析后的数据
        """
        # 查找法术实体
        spell_entities = entities.get_entities_by_type('SPELL')
        
        if spell_entities:
            spell = spell_entities[0]
            return {
                'command_type': 'cast_spell',
                'spell': spell.extraction.name,
                'spell_id': spell.matched_entity.id if spell.matched_entity else None,
                'is_new': spell.is_new,
                'found_entity': True
            }
        else:
            # 从参数推断法术名称
            spell_name = command_data.arguments[0] if command_data.arguments else None
            return {
                'command_type': 'cast_spell',
                'spell': spell_name,
                'spell_id': None,
                'is_new': spell_name is not None,
                'found_entity': False
            }
    
    async def _parse_roll_command(
        self,
        command_data: CommandTaskData
    ) -> Dict[str, Any]:
        """
        解析投骰子指令
        
        Args:
            command_data: 指令数据
            
        Returns:
            Dict: 解析后的数据
        """
        import re
        
        if command_data.arguments:
            # 尝试解析骰子表达式
            dice_pattern = r'^(\d*)d(\d+)([+-]\d+)?$'
            match = re.match(dice_pattern, command_data.arguments[0])
            
            if match:
                return {
                    'command_type': 'roll_dice',
                    'dice_count': int(match.group(1)) if match.group(1) else 1,
                    'dice_size': int(match.group(2)),
                    'modifier': int(match.group(3)) if match.group(3) else 0,
                    'raw_input': command_data.arguments[0]
                }
        
        return {
            'command_type': 'roll_dice',
            'dice_count': 1,
            'dice_size': 20,
            'modifier': 0,
            'raw_input': command_data.arguments[0] if command_data.arguments else None
        }
    
    async def _parse_check_character_command(
        self,
        command_data: CommandTaskData
    ) -> Dict[str, Any]:
        """
        解析查询角色指令
        
        Args:
            command_data: 指令数据
            
        Returns:
            Dict: 解析后的数据
        """
        character_name = command_data.arguments[0] if command_data.arguments else None
        
        return {
            'command_type': 'check_character',
            'character_name': character_name,
            'has_target': character_name is not None
        }


class TaskDispatcher:
    """任务分发器"""
    
    def __init__(self):
        """
        初始化任务分发器
        """
        self.processors: Dict[InputType, TaskProcessor] = {
            InputType.ACTION: ActionProcessor(),
            InputType.DIALOGUE: DialogueProcessor(),
            InputType.THOUGHT: ThoughtProcessor(),
            InputType.OOC: OOCProcessor(),
            InputType.COMMAND: CommandProcessor()
        }
        self.logger = app_logger
    
    async def dispatch(
        self,
        classified_input: ClassifiedInput,
        entities: ExtractedEntity
    ) -> DispatchedTask:
        """
        分发任务
        
        Args:
            classified_input: 分类后的输入
            entities: 抽取的实体
            
        Returns:
            DispatchedTask: 分发的任务
        """
        processor = self.processors.get(classified_input.input_type)
        if not processor:
            raise ValueError(f"未找到处理器: {classified_input.input_type}")
        
        # 处理任务
        task_data = await processor.process(classified_input, entities)
        
        # 创建分发任务
        dispatched_task = DispatchedTask(
            task_id=str(uuid.uuid4()),
            input_type=classified_input.input_type,
            original_input=classified_input,
            entities=entities,
            task_data=task_data,
            requires_npc_response=processor.requires_npc_response(classified_input),
            target_npc_id=processor.get_target_npc(classified_input),
            time_cost=await processor.calculate_time_cost(task_data)
        )
        
        self.logger.info(
            f"分发任务: {dispatched_task.task_id} - "
            f"{classified_input.input_type.value}"
        )
        
        return dispatched_task
    
    async def batch_dispatch(
        self,
        classified_inputs: List[ClassifiedInput],
        entities_list: List[ExtractedEntity]
    ) -> List[DispatchedTask]:
        """
        批量分发任务
        
        Args:
            classified_inputs: 分类后的输入列表
            entities_list: 抽取的实体列表
            
        Returns:
            List[DispatchedTask]: 分发的任务列表
        """
        import asyncio
        
        tasks = []
        for i, classified_input in enumerate(classified_inputs):
            entities = entities_list[i] if i < len(entities_list) else ExtractedEntity(
                original_input=classified_input,
                entities=[]
            )
            tasks.append(self.dispatch(classified_input, entities))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        dispatched_tasks = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"第{i}个任务分发失败: {result}")
                # 创建默认任务
                dispatched_tasks.append(DispatchedTask(
                    task_id=str(uuid.uuid4()),
                    input_type=classified_inputs[i].input_type,
                    original_input=classified_inputs[i],
                    entities=ExtractedEntity(
                        original_input=classified_inputs[i],
                        entities=[]
                    ),
                    task_data=None,
                    requires_npc_response=False,
                    target_npc_id=None,
                    time_cost=timedelta(minutes=1)
                ))
            else:
                dispatched_tasks.append(result)
        
        return dispatched_tasks


# ==================== 工厂函数 ====================

def create_task_dispatcher() -> TaskDispatcher:
    """
    创建任务分发器实例
    
    Returns:
        TaskDispatcher: 任务分发器实例
    """
    return TaskDispatcher()