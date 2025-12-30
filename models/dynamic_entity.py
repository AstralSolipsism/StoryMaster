"""
动态实体模型

提供运行时动态数据结构，替代硬编码的实体类。
基于规则书Schema动态创建和管理实体。
"""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass, field
import json

from ..core.schema_manager import (
    SchemaManager,
    RulebookSchema,
    EntityDefinition,
    PropertyDefinition,
    PropertyType,
)
from ..core.exceptions import ValidationError, DataStorageError


@dataclass
class DynamicEntity:
    """
    动态实体，基于Schema定义
    
    支持运行时动态属性，不依赖于硬编码的类结构。
    """
    
    def __init__(self, entity_type: str, entity_def: EntityDefinition):
        """
        初始化动态实体
        
        Args:
            entity_type: 实体类型
            entity_def: 实体定义
        """
        self._entity_type = entity_type
        self._entity_def = entity_def
        self._id: None
        self._properties = {}
        self._relationships = {}
        self._metadata = {}
        self._created_at = None
        self._updated_at = None
        self._schema = entity_def
        
        logger.debug(f"创建动态实体: {entity_type}")
    
    @property
    def id(self) -> Optional[str]:
        """获取实体ID"""
        return self._id
    
    @property
    def entity_type(self) -> str:
        """获取实体类型"""
        return self._entity_type
    
    @property
    def properties(self) -> Dict[str, Any]:
        """获取实体属性"""
        return self._properties
    
    @property
    def relationships(self) -> Dict[str, Any]:
        """获取实体关系"""
        return self._relationships
    
    @property
    def created_at(self) -> Optional[datetime]:
        """获取创建时间"""
        return self._created_at
    
    @property
    def updated_at(self) -> Optional[datetime]:
        """获取更新时间"""
        return self._updated_at
    
    def set_id(self, entity_id: str) -> None:
        """
        设置实体ID
        
        Args:
            entity_id: 实体唯一ID
        """
        if not entity_id:
            raise ValueError("实体ID不能为空")
        
        self._id = entity_id
        logger.debug(f"设置实体ID: {self._entity_type}:{entity_id}")
    
    def set_property(self, name: str, value: Any, validate: bool = True) -> None:
        """
        设置属性值
        
        Args:
            name: 属性名称
            value: 属性值
            validate: 是否验证值（默认True）
            
        Raises:
            ValueError: 属性不存在或值无效
        """
        prop_def = self._entity_def.properties.get(name)
        
        if not prop_def:
            raise ValueError(f"属性{name}在Schema中未定义")
        
        # 根据Schema验证属性
        if validate:
            self._validate_property(name, value, prop_def)
        
        self._properties[name] = value
        logger.debug(f"设置属性: {self._entity_type}.{name} = {value}")
    
    def get_property(self, name: str, default: Any = None) -> Any:
        """
        获取属性值
        
        Args:
            name: 属性名称
            default: 默认值（如果属性不存在）
            
        Returns:
            属性值或默认值
        """
        return self._properties.get(name, default)
    
    def set_properties(self, properties: Dict[str, Any], validate: bool = True) -> None:
        """
        批量设置属性
        
        Args:
            properties: 属性字典
            validate: 是否验证值（默认True）
            
        Raises:
            ValueError: 任何属性无效
        """
        errors = []
        
        for name, value in properties.items():
            try:
                self.set_property(name, value, validate)
            except ValueError as e:
                errors.append(str(e))
        
        if errors and validate:
            raise ValidationError(f"属性设置失败: {', '.join(errors)}")
        
        logger.debug(f"批量设置属性: {self._entity_type}, 数量: {len(properties)}")
    
    def set_relationship(self, relation_name: str, target_entity_id: str,
                       properties: Optional[Dict[str, Any]] = None) -> None:
        """
        设置关系
        
        Args:
            relation_name: 关系名称
            target_entity_id: 目标实体ID
            properties: 关系属性（可选）
        """
        rel_def = self._entity_def.relationships.get(relation_name)
        
        if not rel_def:
            raise ValueError(f"关系{relation_name}在Schema中未定义")
        
        self._relationships[relation_name] = {
            'target_id': target_entity_id,
            'target_type': rel_def.target_entity_type,
            'properties': properties or {},
            'relation_type': rel_def.relationship_type
        }
        
        logger.debug(f"设置关系: {self._entity_type}.{relation_name} -> {target_entity_id}")
    
    def get_relationship(self, relation_name: str) -> Optional[Dict[str, Any]]:
        """
        获取关系
        
        Args:
            relation_name: 关系名称
            
        Returns:
            关系数据或None
        """
        return self._relationships.get(relation_name)
    
    def get_all_relationships(self) -> Dict[str, Any]:
        """
        获取所有关系
        
        Returns:
            所有关系的字典
        """
        return self._relationships
    
    def validate(self) -> Dict[str, Any]:
        """
        验证实体数据
        
        Returns:
            验证结果 {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str]
            }
        """
        errors = []
        warnings = []
        
        # 验证必需属性
        for prop_name, prop_def in self._entity_def.properties.items():
            if prop_def.required and prop_name not in self._properties:
                errors.append(f"缺少必需属性: {prop_name}")
        
        # 验证属性类型和范围
        for prop_name, value in self._properties.items():
            prop_def = self._entity_def.properties.get(prop_name)
            if prop_def:
                try:
                    self._validate_property_type(prop_name, value, prop_def)
                    self._validate_property_range(prop_name, value, prop_def)
                except ValueError as e:
                    errors.append(str(e))
        
        # 应用Schema中的验证规则
        validation_errors = self._apply_validation_rules(self._properties)
        if validation_errors:
            errors.extend(validation_errors)
        
        # 检查ID
        if not self._id:
            warnings.append("实体ID未设置")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def _validate_property(self, name: str, value: Any, prop_def: PropertyDefinition) -> None:
        """
        验证单个属性
        
        Args:
            name: 属性名称
            value: 属性值
            prop_def: 属性定义
            
        Raises:
            ValueError: 属性值无效
        """
        if value is None:
            if prop_def.default is not None:
                raise ValueError(f"属性{name}不能为None（无默认值）")
            return
        
        prop_type = prop_def.type
        
        # 类型验证
        if prop_type == PropertyType.STRING and not isinstance(value, str):
            raise ValueError(f"属性{name}必须是字符串: {type(value)}")
        elif prop_type in [PropertyType.INTEGER, PropertyType.NUMBER] and not isinstance(value, (int, float)):
            raise ValueError(f"属性{name}必须是数字: {type(value)}")
        elif prop_type == PropertyType.BOOLEAN and not isinstance(value, bool):
            raise ValueError(f"属性{name}必须是布尔值: {type(value)}")
        elif prop_type == PropertyType.ARRAY and not isinstance(value, list):
            raise ValueError(f"属性{name}必须是数组: {type(value)}")
        elif prop_type == PropertyType.OBJECT and not isinstance(value, dict):
            raise ValueError(f"属性{name}必须是对象: {type(value)}")
        
        # 范围验证
        if prop_def.min_value is not None and value < prop_def.min_value:
            raise ValueError(f"属性{name}不能小于{prop_def.min_value}: {value}")
        if prop_def.max_value is not None and value > prop_def.max_value:
            raise ValueError(f"属性{name}不能大于{prop_def.max_value}: {value}")
        
        # 枚举值验证
        if prop_def.enum_values and value not in prop_def.enum_values:
            raise ValueError(f"属性{name}的值不在允许范围内: {value}")
        
        # 正则表达式验证
        if prop_def.validation_regex and not isinstance(value, str):
            import re
            if not re.match(prop_def.validation_regex, value):
                raise ValueError(f"属性{name}不符合要求的格式")
    
    def _validate_property_type(self, name: str, value: Any, prop_def: PropertyDefinition) -> None:
        """验证属性类型"""
        # 类型验证在_validate_property中已经处理
        pass
    
    def _validate_property_range(self, name: str, value: Any, prop_def: PropertyDefinition) -> None:
        """验证属性范围"""
        # 范围验证在_validate_property中已经处理
        pass
    
    def _apply_validation_rules(self, properties: Dict[str, Any]) -> List[str]:
        """
        应用Schema中的验证规则
        
        Args:
            properties: 属性字典
            
        Returns:
            错误消息列表
        """
        errors = []
        validation_rules = self._entity_def.validation_rules
        
        for rule_name, rule_config in validation_rules.items():
            try:
                self._apply_rule(rule_name, rule_config, properties)
            except ValueError as e:
                errors.append(str(e))
        
        return errors
    
    def _apply_rule(self, rule_name: str, rule_config: Dict[str, Any], 
                 properties: Dict[str, Any]) -> None:
        """
        应用单个验证规则
        
        Args:
            rule_name: 规则名称
            rule_config: 规则配置
            properties: 属性字典
            
        Raises:
            ValueError: 规则验证失败
        """
        rule_type = rule_config.get('type')
        
        if rule_type == 'required_value':
            default_value = rule_config.get('value')
            if default_value is not None and rule_name not in properties:
                raise ValueError(f"缺少必需的属性: {rule_name}")
        
        elif rule_type == 'formula':
            formula = rule_config.get('formula')
            if formula:
                calculated_value = self._evaluate_formula(formula, properties)
                if calculated_value is not None:
                    # 不直接设置属性，只验证结果
                    if isinstance(calculated_value, bool) and not calculated_value:
                        raise ValueError(f"公式{rule_name}计算结果为False")
                elif not isinstance(calculated_value, bool):
                    errors.append(f"公式{rule_name}计算结果无效")
        
        elif rule_type == 'depends_on':
            depends_on = rule_config.get('depends_on', [])
            for dep_prop in depends_on:
                if dep_prop not in properties or not properties[dep_prop]:
                    raise ValueError(f"属性{rule_name}依赖于{dep_prop}，但该属性未设置或为假")
    
        elif rule_type == 'mutually_exclusive':
            exclusive_props = rule_config.get('exclusive_props', [])
            set_count = sum(1 for prop in exclusive_props if properties.get(prop, False))
            if set_count > 1:
                raise ValueError(f"属性{rule_name}中的互斥属性只能设置一个: {exclusive_props}")
    
    def _evaluate_formula(self, formula: str, properties: Dict[str, Any]) -> Any:
        """
        评估公式表达式
        
        Args:
            formula: 公式字符串
            properties: 属性字典
            
        Returns:
            计算结果
        """
        try:
            # 替换公式中的占位符
            expr = formula
            for prop_name, prop_value in properties.items():
                if prop_value is not None:
                    expr = expr.replace(f'{{{prop_name}}}', str(prop_value))
            
            # 安全评估公式
            # 注意：生产环境应该使用更安全的表达式解析器
            result = eval(expr, {"__builtins__": {"max": max, "min": min, "abs": abs}})
            return result
        except Exception as e:
            logger.warning(f"公式评估失败: {formula}, 错误: {e}")
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            包含实体所有信息的字典
        """
        return {
            'id': self._id,
            'entity_type': self._entity_type,
            'properties': self._properties,
            'relationships': self._relationships,
            'metadata': self._metadata,
            'created_at': self._created_at.isoformat() if self._created_at else None,
            'updated_at': self._updated_at.isoformat() if self._updated_at else None,
        }
    
    def to_json(self) -> str:
        """
        转换为JSON字符串
        
        Returns:
            JSON格式的实体数据
        """
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """
        从字典加载实体数据
        
        Args:
            data: 包含实体数据的字典
        """
        self._id = data.get('id')
        self._properties = data.get('properties', {})
        self._relationships = data.get('relationships', {})
        self._metadata = data.get('metadata', {})
        
        # 解析时间
        if data.get('created_at'):
            self._created_at = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            self._updated_at = datetime.fromisoformat(data['updated_at'])
    
    def get_schema(self) -> EntityDefinition:
        """
        获取实体的Schema定义
        
        Returns:
            EntityDefinition: 实体定义对象
        """
        return self._entity_def
    
    def copy(self) -> 'DynamicEntity':
        """
        创建实体的深拷贝
        
        Returns:
            新的DynamicEntity实例
        """
        new_entity = DynamicEntity(self._entity_type, self._entity_def)
        new_entity._id = self._id
        new_entity._properties = self._properties.copy()
        new_entity._relationships = self._relationships.copy()
        new_entity._metadata = self._metadata.copy()
        new_entity._created_at = self._created_at
        new_entity._updated_at = self._updated_at
        
        return new_entity


# 添加日志支持
import logging
logger = logging.getLogger(__name__)

# 导出类
__all__ = [
    "DynamicEntity",
]