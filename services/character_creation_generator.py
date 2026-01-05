"""
角色卡创建表单生成器（简化版）
直接使用预生成的创建模型
"""

from typing import Dict, Any, List, Optional
from ..core.logging import app_logger
from ..core.exceptions import ValidationError
from ..models.character_creation_models import (
    CharacterCreationModel,
    CharacterCreationFormResponse,
    CharacterCreationFormRequest
)
from ..models.rulebook_models import CompleteRulebookData


class CharacterCreationGenerator:
    """角色卡创建表单生成器（简化版）"""
    
    def __init__(self, rulebook_manager):
        self.rulebook_manager = rulebook_manager
        self.logger = app_logger
    
    async def get_creation_form(
        self,
        schema_id: str,
        user_id: str,
        entity_type: str = "Character"
    ) -> Dict[str, Any]:
        """
        获取角色卡创建表单
        
        注意：不再需要从Schema中提取，直接使用预生成的创建模型
        
        Args:
            schema_id: 规则书Schema ID
            user_id: 用户ID
            entity_type: 实体类型（默认为Character）
            
        Returns:
            Dict: 创建表单数据
        """
        try:
            # 加载规则书数据
            rulebook_data = await self.rulebook_manager.download_schema(schema_id)
            
            if not rulebook_data:
                raise ValidationError(f"规则书不存在: {schema_id}")
            
            # 提取角色卡创建模型
            creation_model = rulebook_data.get('character_creation_model')
            
            if not creation_model:
                # 降级方案：从完整Schema生成基本模型
                self.logger.warning(f"规则书{schema_id}未包含创建模型，使用降级方案")
                return await self._generate_fallback_form(rulebook_data, entity_type)
            
            # 转换为表单格式
            form_data = self._convert_model_to_form(creation_model)
            
            self.logger.info(f"创建表单生成成功: {schema_id}")
            return form_data
            
        except Exception as e:
            self.logger.error(f"生成创建表单失败: {e}", exc_info=True)
            raise ValidationError(f"生成创建表单失败: {str(e)}")
    
    def _convert_model_to_form(
        self,
        creation_model: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        将创建模型转换为前端表单格式
        
        Args:
            creation_model: 角色卡创建模型
            
        Returns:
            Dict: 前端表单数据
        """
        warnings = []
        
        return {
            # 模型信息
            "model_id": creation_model.get('model_id', ''),
            "model_name": creation_model.get('model_name', ''),
            "model_description": creation_model.get('model_description', ''),
            
            # 字段定义（按显示顺序排序）
            "fields": [
                {
                    **field_data,
                    "field_name": field_name
                }
                for field_name, field_data in sorted(
                    creation_model.get('fields', {}).items(),
                    key=lambda x: x[1].get('display_order', 0)
                )
            ],
            
            # 字段分组
            "field_groups": creation_model.get('field_groups', []),
            
            # 验证规则
            "validation_rules": creation_model.get('validation_rules', []),
            
            # 计算规则
            "calculation_rules": creation_model.get('calculation_rules', []),
            
            # 模板数据
            "templates": creation_model.get('templates', {}),
            
            # 元数据
            "metadata": creation_model.get('metadata', {}),
            
            # 警告信息
            "warnings": warnings
        }
    
    async def _generate_fallback_form(
        self,
        rulebook_data: Dict[str, Any],
        entity_type: str
    ) -> Dict[str, Any]:
        """
        降级方案：从完整Schema生成基本创建表单
        
        Args:
            rulebook_data: 完整的规则书数据
            entity_type: 实体类型
            
        Returns:
            Dict: 基本创建表单数据
        """
        warnings = []
        
        # 从Schema中提取实体定义
        entities = rulebook_data.get('rulebook_schema', {}).get('entities', {})
        entity_def = entities.get(entity_type)
        
        if not entity_def:
            raise ValidationError(f"规则书Schema中未找到实体: {entity_type}")
        
        # 从实体属性生成字段
        properties = entity_def.get('properties', {})
        fields = []
        
        field_order = 0
        for prop_name, prop_def in properties.items():
            # 跳过复杂类型
            if prop_def.get('type') == 'object':
                continue
            
            field = {
                "field_name": prop_name,
                "type": prop_def.get('type', 'string'),
                "label": prop_def.get('description', prop_name),
                "description": prop_def.get('description', ''),
                "required": prop_def.get('required', False),
                "default": prop_def.get('default'),
                "display_order": field_order,
                "ui_type": "input"
            }
            
            # 添加UI建议
            field_type = prop_def.get('type', 'string')
            if field_type == 'integer':
                field['ui_options'] = {"step": 1}
            elif field_type == 'number':
                field['ui_options'] = {"step": 0.1}
            elif field_type == 'boolean':
                field['ui_type'] = 'checkbox'
            elif field_type == 'array' or field_type == 'object':
                field['ui_type'] = 'textarea'
            
            fields.append(field)
            field_order += 1
        
        warnings.append("使用降级方案：部分功能可能受限")
        
        return {
            "model_id": f"fallback_{entity_type}",
            "model_name": f"{entity_type}创建（降级）",
            "model_description": "从规则书Schema生成的简化模型",
            "fields": fields,
            "field_groups": [{
                "name": "basic_info",
                "label": "基本信息",
                "display_order": 1,
                "fields": [field['field_name'] for field in fields]
            }],
            "validation_rules": [],
            "calculation_rules": [],
            "templates": {},
            "metadata": {
                "fallback_mode": True,
                "generated_from": "schema"
            },
            "warnings": warnings
        }


# 工厂函数
def create_character_creation_generator(rulebook_manager) -> CharacterCreationGenerator:
    """创建角色卡生成器"""
    return CharacterCreationGenerator(rulebook_manager)


# 导出函数
__all__ = [
    "CharacterCreationGenerator",
    "create_character_creation_generator"
]