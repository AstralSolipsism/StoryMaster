"""
规则计算器（修订版）
使用预生成的角色卡创建模型中的计算规则
"""

from typing import Dict, Any, List
from ..core.logging import app_logger
from ..core.exceptions import ValidationError
from ..models.character_creation_models import (
    CharacterCreationModel,
    CreationCalculationRule,
    CalculatedCharacterData
)


class RuleCalculator:
    """规则计算引擎（使用创建模型中的计算规则）"""
    
    def __init__(self, character_creation_model: CharacterCreationModel):
        """
        初始化计算器
        
        Args:
            character_creation_model: 角色卡创建模型
        """
        self.creation_model = character_creation_model
        self.logger = app_logger
    
    async def calculate_character_properties(
        self,
        character_data: Dict[str, Any]
    ) -> CalculatedCharacterData:
        """
        计算角色属性
        
        Args:
            character_data: 原始角色数据（用户输入）
            
        Returns:
            CalculatedCharacterData: 计算后的角色数据
        """
        try:
            # 初始化计算属性
            calculated_properties = character_data.copy()
            derived_values = {}
            
            # 获取计算规则
            calculation_rules = self.creation_model.calculation_rules
            
            # 应用所有计算规则
            for rule in calculation_rules:
                if not rule.auto_apply:
                    continue
                
                # 检查依赖字段是否都存在
                dependencies_met = all(
                    dep in character_data 
                    for dep in rule.input_fields
                )
                
                if not dependencies_met:
                    self.logger.warning(
                        f"计算规则{rule.name}缺少依赖字段，跳过: {rule.input_fields}"
                    )
                    continue
                
                # 执行计算
                try:
                    result = await self._calculate_formula(
                        rule.formula,
                        calculated_properties,
                        rule.parameters
                    )
                    
                    calculated_properties[rule.output_field] = result
                    
                    # 记录派生值
                    derived_values[rule.output_field] = {
                        'formula': rule.formula,
                        'display_formula': rule.display_formula,
                        'description': rule.description,
                        'value': result,
                        'input_fields': rule.input_fields,
                        'rule_name': rule.name
                    }
                    
                    self.logger.debug(
                        f"计算规则{rule.name}执行成功: {rule.output_field} = {result}"
                    )
                    
                except Exception as e:
                    self.logger.error(
                        f"计算规则{rule.name}执行失败: {e}"
                    )
                    continue
            
            # 特殊处理：属性修正值计算（简化实现）
            await self._calculate_ability_modifiers(calculated_properties, derived_values)
            
            # 特殊处理：熟练度加值计算
            await self._calculate_proficiency_bonus(calculated_properties, derived_values)
            
            self.logger.info(f"角色属性计算完成，共计算{len(derived_values)}个派生值")
            
            return CalculatedCharacterData(
                character_id=character_data.get('character_id', ''),
                base_properties=character_data,
                calculated_properties=calculated_properties,
                derived_values=derived_values,
                validation_warnings=[]
            )
            
        except Exception as e:
            self.logger.error(f"角色属性计算失败: {e}", exc_info=True)
            raise ValidationError(f"角色属性计算失败: {str(e)}")
    
    async def _calculate_formula(
        self,
        formula: str,
        properties: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Any:
        """
        计算公式
        
        Args:
            formula: 公式表达式
            properties: 属性字典
            parameters: 公式参数
            
        Returns:
            Any: 计算结果
        """
        try:
            # 准备计算上下文
            import math
            context = {
                "__builtins__": {
                    "max": max,
                    "min": min,
                    "abs": abs,
                    "sum": sum,
                    "floor": lambda x: math.floor(x),
                    "ceil": lambda x: math.ceil(x),
                    "round": lambda x: round(x),
                    "len": len
                },
                "math": math
            }
            
            # 添加所有属性到上下文
            for prop_name, prop_value in properties.items():
                if isinstance(prop_value, (int, float, str, bool)):
                    context[prop_name] = prop_value
            
            # 添加参数到上下文
            for param_name, param_value in parameters.items():
                if isinstance(param_value, (int, float, str, bool)):
                    context[param_name] = param_value
            
            # 处理嵌套对象（如ability_scores）
            for prop_name, prop_value in properties.items():
                if isinstance(prop_value, dict):
                    for sub_key, sub_value in prop_value.items():
                        if isinstance(sub_value, (int, float, str, bool)):
                            context[f"{prop_name}_{sub_key}"] = sub_value
            
            # 执行计算
            result = eval(formula, context)
            
            return result
            
        except Exception as e:
            raise ValueError(f"公式计算失败: {formula}, 错误: {str(e)}")
    
    async def _calculate_ability_modifiers(
        self,
        properties: Dict[str, Any],
        derived_values: Dict[str, Any]
    ) -> None:
        """计算属性修正值"""
        # 检查是否有ability_scores属性
        if 'ability_scores' in properties:
            ability_scores = properties['ability_scores']
            
            # 为每个属性计算修正值
            for ability_name, score in ability_scores.items():
                if isinstance(score, (int, float)):
                    modifier = int((score - 10) / 2)
                    properties[f"{ability_name}_modifier"] = modifier
                    
                    # 记录到派生值
                    derived_values[f"{ability_name}_modifier"] = {
                        'formula': 'floor((ability - 10) / 2)',
                        'display_formula': '⌊(属性 - 10) / 2⌋',
                        'description': f'{ability_name}修正值',
                        'value': modifier,
                        'input_fields': [ability_name],
                        'rule_name': 'ability_modifier_calculation'
                    }
                    
                    self.logger.debug(
                        f"{ability_name}修正值计算: {score} -> {modifier}"
                    )
    
    async def _calculate_proficiency_bonus(
        self,
        properties: Dict[str, Any],
        derived_values: Dict[str, Any]
    ) -> None:
        """计算熟练度加值"""
        if 'level' in properties:
            level = properties['level']
            if isinstance(level, (int, float)):
                # D&D 5e 熟练度加值公式
                proficiency_bonus = int((level - 1) / 4) + 2
                properties['proficiency_bonus'] = proficiency_bonus
                
                # 记录到派生值
                derived_values['proficiency_bonus'] = {
                    'formula': 'floor((level - 1) / 4) + 2',
                    'display_formula': '⌊(等级 - 1) / 4⌋ + 2',
                    'description': '熟练度加值',
                    'value': proficiency_bonus,
                    'input_fields': ['level'],
                    'rule_name': 'proficiency_bonus_calculation'
                }
                
                self.logger.debug(
                    f"熟练度加值计算: level {level} -> {proficiency_bonus}"
                )
    
    def set_character_creation_model(self, creation_model: CharacterCreationModel) -> None:
        """设置角色卡创建模型"""
        self.creation_model = creation_model
        self.logger.info(f"角色卡创建模型已更新: {creation_model.model_id}")


# 工厂函数
def create_rule_calculator(creation_model: CharacterCreationModel) -> RuleCalculator:
    """创建规则计算器"""
    return RuleCalculator(creation_model)


# 导出函数
__all__ = [
    "RuleCalculator",
    "CalculatedCharacterData",
    "create_rule_calculator"
]