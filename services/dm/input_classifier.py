"""
输入分类器
使用LLM对玩家输入进行智能分类
"""

import json
import logging
from typing import Dict, Any, List, Optional

from ...models.dm_models import (
    PlayerInput,
    ClassifiedInput,
    InputType
)
from ...core.logging import app_logger
from ...provider import ProviderManager, ProviderRequest, ChatMessage


class InputClassifier:
    """玩家输入分类器"""
    
    def __init__(
        self,
        model_scheduler: ProviderManager,
        temperature: float = 0.3
    ):
        """
        初始化输入分类器
        
        Args:
            model_scheduler: 模型调度器
            temperature: 温度参数（影响分类的一致性）
        """
        self.model_scheduler = model_scheduler
        self.temperature = temperature
        self.logger = app_logger
    
    async def classify(
        self,
        input_data: PlayerInput
    ) -> ClassifiedInput:
        """
        分类玩家输入
        
        输入类型：
        - ACTION: 行为描述（施法、鉴定、移动等）
        - DIALOGUE: 对话内容（角色发言）
        - THOUGHT: 心理描述
        - OOC: 场外发言（玩家间交流）
        - COMMAND: 指令（/回合结束、/施法等）
        
        Args:
            input_data: 玩家输入数据
            
        Returns:
            ClassifiedInput: 分类结果
        """
        try:
            # 检查是否是命令
            if self._is_command(input_data.content):
                return self._classify_as_command(input_data)
            
            # 使用LLM进行分类
            classification_result = await self._classify_with_llm(input_data)
            
            # 构建分类结果
            classified = ClassifiedInput(
                original_input=input_data,
                input_type=InputType(classification_result['type']),
                confidence=classification_result.get('confidence', 0.8),
                entities=classification_result.get('entities', []),
                action_type=classification_result.get('action_type'),
                target=classification_result.get('target')
            )
            
            self.logger.info(
                f"输入分类成功: {input_data.content[:50]}... -> {classified.input_type.value}"
            )
            
            return classified
            
        except Exception as e:
            self.logger.error(f"输入分类失败: {e}", exc_info=True)
            # 返回默认分类
            return ClassifiedInput(
                original_input=input_data,
                input_type=InputType.ACTION,
                confidence=0.0,
                entities=[],
                action_type=None,
                target=None
            )
    
    def _is_command(self, content: str) -> bool:
        """
        检查是否是命令
        
        Args:
            content: 输入内容
            
        Returns:
            bool: 是否是命令
        """
        return content.strip().startswith('/')
    
    def _classify_as_command(self, input_data: PlayerInput) -> ClassifiedInput:
        """
        分类为命令类型
        
        Args:
            input_data: 玩家输入数据
            
        Returns:
            ClassifiedInput: 分类结果
        """
        command_parts = input_data.content.strip().split(maxsplit=1)
        command = command_parts[0]
        
        return ClassifiedInput(
            original_input=input_data,
            input_type=InputType.COMMAND,
            confidence=1.0,
            entities=[],
            action_type=command,
            target=None
        )
    
    async def _classify_with_llm(
        self,
        input_data: PlayerInput
    ) -> Dict[str, Any]:
        """
        使用LLM进行分类
        
        Args:
            input_data: 玩家输入数据
            
        Returns:
            Dict: 分类结果
        """
        # 构建分类提示词
        prompt = self._build_classification_prompt(input_data)
        
        # 调用LLM
        request_context = ProviderRequest(
            messages=[
                ChatMessage(
                    role='system',
                    content='你是一个专业的D&D游戏输入分类器。请准确分类玩家输入，并以JSON格式返回结果。'
                ),
                ChatMessage(
                    role='user',
                    content=prompt
                )
            ],
            max_tokens=500,
            temperature=self.temperature
        )
        
        response = await self.model_scheduler.chat(request_context)
        
        if not response.choices or not response.choices[0].message.content:
            raise ValueError("LLM响应为空")
        
        # 解析JSON响应
        try:
            result = json.loads(response.choices[0].message.content)
            self._validate_classification_result(result)
            return result
        except json.JSONDecodeError as e:
            self.logger.warning(f"LLM返回的JSON格式错误: {e}")
            # 返回默认分类
            return {
                'type': 'action',
                'confidence': 0.5,
                'entities': [],
                'action_type': None,
                'target': None
            }
    
    def _build_classification_prompt(
        self,
        input_data: PlayerInput
    ) -> str:
        """
        构建分类提示词
        
        Args:
            input_data: 玩家输入数据
            
        Returns:
            str: 提示词
        """
        return f"""请对以下玩家输入进行分类：

玩家角色: {input_data.character_name}
输入内容: {input_data.content}

分类类型：
- ACTION: 行为描述（如：施法、鉴定、移动、攻击、检定等）
- DIALOGUE: 对话内容（如：角色说话、询问等）
- THOUGHT: 心理描述（如：角色内心想法、思考等）
- OOC: 场外发言（如：玩家间交流、规则询问等）

请以JSON格式返回，包含以下字段：
- type: 输入类型（action/dialogue/thought/ooc）
- confidence: 置信度（0.0-1.0）
- entities: 提及的实体列表（如有）
  - name: 实体名称
  - type: 实体类型（NPC/玩家/物品等）
- action_type: 动作类型（如果是ACTION类型，如cast_spell/check/move等）
- target: 目标对象（如有）
  - name: 目标名称
  - type: 目标类型

示例：
输入: "我对商人说：请问这把剑多少钱？"
输出: {{"type": "dialogue", "confidence": 0.95, "entities": [{"name": "商人", "type": "NPC"}], "action_type": null, "target": {"name": "商人", "type": "NPC"}}}

输入: "我施放火球术攻击哥布林"
输出: {{"type": "action", "confidence": 0.9, "entities": [{"name": "火球术", "type": "SPELL"}, {"name": "哥布林", "type": "MONSTER"}], "action_type": "cast_spell", "target": {"name": "哥布林", "type": "MONSTER"}}}

现在请分类：
"""
    
    def _validate_classification_result(self, result: Dict[str, Any]) -> None:
        """
        验证分类结果
        
        Args:
            result: 分类结果
            
        Raises:
            ValueError: 如果结果无效
        """
        if 'type' not in result:
            raise ValueError("分类结果缺少type字段")
        
        valid_types = ['action', 'dialogue', 'thought', 'ooc', 'command']
        if result['type'] not in valid_types:
            raise ValueError(f"无效的输入类型: {result['type']}")
        
        if 'confidence' not in result:
            raise ValueError("分类结果缺少confidence字段")
        
        confidence = result['confidence']
        if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            raise ValueError(f"置信度必须在0.0-1.0之间: {confidence}")
    
    async def batch_classify(
        self,
        inputs: List[PlayerInput]
    ) -> List[ClassifiedInput]:
        """
        批量分类玩家输入
        
        Args:
            inputs: 玩家输入列表
            
        Returns:
            List[ClassifiedInput]: 分类结果列表
        """
        import asyncio
        
        tasks = [self.classify(input_data) for input_data in inputs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        classified_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"第{i}个输入分类失败: {result}")
                # 返回默认分类
                classified_results.append(ClassifiedInput(
                    original_input=inputs[i],
                    input_type=InputType.ACTION,
                    confidence=0.0,
                    entities=[],
                    action_type=None,
                    target=None
                ))
            else:
                classified_results.append(result)
        
        return classified_results


# ==================== 工厂函数 ====================

def create_input_classifier(
    model_scheduler: ProviderManager,
    temperature: float = 0.3
) -> InputClassifier:
    """
    创建输入分类器实例
    
    Args:
        model_scheduler: 模型调度器
        temperature: 温度参数
        
    Returns:
        InputClassifier: 输入分类器实例
    """
    return InputClassifier(
        model_scheduler=model_scheduler,
        temperature=temperature
    )