"""
角色卡创建数据验证器（修订版）
使用预生成的角色卡创建模型中的验证规则
"""

from typing import Dict, Any, List
from ..core.logging import app_logger
from ..core.exceptions import ValidationError
from ..models.character_creation_models import (
    CharacterCreationModel,
    CreationValidationRule,
    ValidationResult
)


class CharacterCreationValidator:
    """角色卡数据验证器（使用创建模型）"""
    
    def __init__(self, character_creation_model: CharacterCreationModel):
        """
        初始化验证器
        
        Args:
            character_creation_model: 角色卡创建模型
        """
        self.character_creation_model = character_creation_model
        self.logger = app_logger
    
    async def validate_character_data(
        self,
        character_data: Dict[str, Any]
    ) -> ValidationResult:
        """
        验证角色数据（使用创建模型中的验证规则）
        
        Args:
            character_data: 角色数据
            
        Returns:
            ValidationResult: 验证结果
        """
        errors = []
        warnings = []
        
        # 验证字段存在性和类型
        field_errors = await self._validate_fields(character_data)
        errors.extend(field_errors['errors'])
        warnings.extend(field_errors['warnings'])
        
        # 应用验证规则
        validation_errors = await self._apply_validation_rules(character_data)
        errors.extend(validation_errors)
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    async def _validate_fields(
        self,
        character_data: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """验证字段定义"""
        errors = []
        warnings = []
        
        fields = self.character_creation_model.fields
        
        for field_name, field_def in fields.items():
            # 检查必填字段
            if field_def.required and field_name not in character_data:
                errors.append(f"缺少必填字段: {field_def.label}")
            
            # 检查字段类型
            if field_name in character_data:
                value = character_data[field_name]
                type_valid = self._validate_field_type(field_def, value)
                if not type_valid:
                    errors.append(f"字段{field_def.label}类型错误: 期望{field_def.type}, 实际{type(value)}")
                
                # 检查字段范围
                range_valid = self._validate_field_range(field_def, value)
                if not range_valid:
                    errors.append(f"字段{field_def.label}值超出范围: {value}")
                
                # 检查枚举值
                if field_def.enum_options:
                    enum_valid = self._validate_enum_value(field_def, value)
                    if not enum_valid:
                        errors.append(f"字段{field_def.label}值不在允许范围内: {value}")
                
                # 检查正则表达式
                if field_def.pattern:
                    regex_valid = self._validate_pattern(field_def, value)
                    if not regex_valid:
                        errors.append(f"字段{field_def.label}格式不正确: {value}")
                
                # 检查只读字段是否被修改
                if field_def.read_only and field_name in character_data:
                    warnings.append(f"字段{field_def.label}为只读，不应由用户输入")
        
        return {'errors': errors, 'warnings': warnings}
    
    def _validate_field_type(self, field_def: Any, value: Any) -> bool:
        """验证字段类型"""
        if value is None:
            return not field_def.required
        
        type_mapping = {
            'string': str,
            'integer': int,
            'number': (int, float),
            'boolean': bool,
            'array': list,
            'object': dict
        }
        
        expected_type = type_mapping.get(field_def.type, object)
        return isinstance(value, expected_type)
    
    def _validate_field_range(self, field_def: Any, value: Any) -> bool:
        """验证字段范围"""
        if value is None:
            return True
        
        try:
            if field_def.min_value is not None:
                if value < field_def.min_value:
                    return False
            
            if field_def.max_value is not None:
                if value > field_def.max_value:
                    return False
            
            if field_def.min_length is not None and isinstance(value, str):
                if len(value) < field_def.min_length:
                    return False
            
            if field_def.max_length is not None and isinstance(value, str):
                if len(value) > field_def.max_length:
                    return False
            
            return True
        except TypeError:
            return False
    
    def _validate_enum_value(self, field_def: Any, value: Any) -> bool:
        """验证枚举值"""
        if not field_def.enum_options:
            return True
        
        enum_values = [opt.get('value') for opt in field_def.enum_options]
        return value in enum_values
    
    def _validate_pattern(self, field_def: Any, value: Any) -> bool:
        """验证正则表达式"""
        if not field_def.pattern or value is None:
            return True
        
        try:
            import re
            return bool(re.match(field_def.pattern, str(value)))
        except Exception:
            return False
    
    async def _apply_validation_rules(
        self,
        character_data: Dict[str, Any]
    ) -> List[str]:
        """应用验证规则"""
        errors = []
        
        validation_rules = self.character_creation_model.validation_rules
        
        for rule in validation_rules:
            # 检查规则是否适用
            if rule.applicable_fields:
                applicable = any(
                    field in character_data 
                    for field in rule.applicable_fields
                )
                
                if applicable:
                    try:
                        valid = await self._evaluate_validation_expression(
                            rule.expression,
                            character_data
                        )
                        if not valid:
                            errors.append(rule.error_message)
                    except Exception as e:
                        self.logger.warning(f"验证规则{rule.name}执行失败: {e}")
                        errors.append(f"验证规则{rule.name}执行失败")
        
        return errors
    
    async def _evaluate_validation_expression(
        self,
        expression: str,
        character_data: Dict[str, Any]
    ) -> bool:
        """
        评估验证表达式
        
        注意：这是一个简化的实现，生产环境应该使用更安全的表达式解析器
        """
        try:
            # 替换表达式中的变量
            expr = expression
            
            # 替换字段值
            for field_name, value in character_data.items():
                if isinstance(value, (str, int, float, bool)):
                    # 处理嵌套对象
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if isinstance(sub_value, (str, int, float, bool)):
                                expr = expr.replace(f"{{{field_name}.{sub_key}}}", str(sub_value))
                    else:
                        expr = expr.replace(f"{{{field_name}}}", str(value))
            
            # 处理函数调用
            import math
            context = {
                "__builtins__": {
                    "max": max,
                    "min": min,
                    "abs": abs,
                    "sum": sum,
                    "floor": lambda x: math.floor(x),
                    "ceil": lambda x: math.ceil(x),
                    "len": len,
                    "bool": bool,
                    "int": int,
                    "float": float,
                    "str": str
                },
                "math": math
            }
            
            # 执行表达式
            result = eval(expr, context)
            return bool(result)
            
        except Exception as e:
            self.logger.warning(f"规则表达式评估失败: {expression}, 错误: {e}")
            return False


# 导出函数
__all__ = [
    "CharacterCreationValidator",
    "ValidationResult"
]