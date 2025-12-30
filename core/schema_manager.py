"""
规则书Schema管理系统

负责管理游戏规则书的Schema定义，包括：
- Schema加载和验证
- 动态实体类型定义
- 属性和关系配置
- 规则计算引擎
"""

import json
import logging
import hashlib
from typing import Dict, List, Optional, Any, Union, Type
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import settings
from .exceptions import ValidationError, DataStorageError

logger = logging.getLogger(__name__)


# ==================== 数据结构定义 ====================

@dataclass
class PropertyDefinition:
    """属性定义"""
    name: str
    type: str  # string, integer, number, boolean, array, object
    required: bool = True
    default: Any = None
    description: str = ""
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    enum_values: Optional[List[str]] = None
    validation_regex: Optional[str] = None


@dataclass
class RelationshipDefinition:
    """关系定义"""
    name: str
    target_entity_type: str
    relationship_type: str  # one_to_one, one_to_many, many_to_many
    inverse_relationship: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None


@dataclass
class EntityDefinition:
    """实体定义"""
    entity_type: str
    label: str  # 显示标签
    plural_label: str  # 复数标签
    properties: Dict[str, PropertyDefinition] = field(default_factory=dict)
    relationships: Dict[str, RelationshipDefinition] = field(default_factory=dict)
    validation_rules: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleDefinition:
    """规则定义"""
    name: str
    type: str  # formula, validation, constraint, calculation
    description: str = ""
    expression: str = ""  # 公式或表达式
    parameters: Dict[str, Any] = field(default_factory=dict)
    applicable_to: Optional[List[str]] = None  # 适用属性


@dataclass
class RulebookSchema:
    """规则书Schema"""
    schema_id: str
    name: str
    version: str
    author: str
    description: str = ""
    game_system: str  # D&D, Pathfinder, etc.
    
    # 实体定义
    entities: Dict[str, EntityDefinition] = field(default_factory=dict)
    
    # 规则定义
    rules: Dict[str, RuleDefinition] = field(default_factory=dict)
    
    # 元数据
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = False
    
    # Schema标识
    @property
    def hash_id(self) -> str:
        """生成Schema的唯一标识"""
        content = f"{self.schema_id}:{self.version}"
        return hashlib.sha256(content.encode()).hexdigest()


class PropertyType:
    """属性类型枚举"""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    DYNAMIC = "dynamic"  # 动态类型，运行时确定


class RelationshipType:
    """关系类型"""
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"
    MANY_TO_ONE = "many_to_one"


class RuleType:
    """规则类型"""
    FORMULA = "formula"  # 计算公式
    VALIDATION = "validation"  # 验证规则
    CONSTRAINT = "constraint"  # 约束条件
    CALCULATION = "calculation"  # 复杂计算


# ==================== Schema管理器 ====================

class SchemaManager:
    """Schema管理器
    
    负责加载、验证、缓存规则书Schema
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化Schema管理器
        
        Args:
            storage_path: Schema存储路径
        """
        self.storage_path = storage_path or "./data/rulebooks"
        self._schemas_cache: Dict[str, RulebookSchema] = {}
        self._active_schema_id: Optional[str] = None
        
        # 确保存储目录存在
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
    
    async def load_schema(self, schema_id: str) -> RulebookSchema:
        """
        加载指定的规则书Schema
        
        Args:
            schema_id: SchemaID
            
        Returns:
            RulebookSchema: 规则书Schema对象
            
        Raises:
            ValidationError: Schema验证失败
            DataStorageError: Schema存储失败
        """
        # 检查缓存
        if schema_id in self._schemas_cache:
            logger.debug(f"从缓存加载Schema: {schema_id}")
            return self._schemas_cache[schema_id]
        
        try:
            # 从文件系统加载Schema
            schema = await self._load_schema_from_file(schema_id)
            
            # 验证Schema
            await self._validate_schema(schema)
            
            # 缓存Schema
            self._schemas_cache[schema_id] = schema
            
            logger.info(f"成功加载Schema: {schema_id}")
            return schema
            
        except Exception as e:
            logger.error(f"加载Schema失败: {schema_id}, 错误: {e}")
            raise DataStorageError(f"加载Schema失败: {e}")
    
    async def _load_schema_from_file(self, schema_id: str) -> RulebookSchema:
        """
        从文件系统加载Schema
        
        Args:
            schema_id: SchemaID
            
        Returns:
            RulebookSchema: 规则书Schema对象
        """
        import os
        import json
        
        # 构建文件路径
        schema_file = os.path.join(self.storage_path, f"{schema_id}.json")
        
        if not os.path.exists(schema_file):
            raise ValidationError(f"Schema文件不存在: {schema_file}")
        
        # 读取并解析JSON
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_data = json.load(f)
        
        # 创建Schema对象
        return self._parse_schema_data(schema_id, schema_data)
    
    def _parse_schema_data(self, schema_id: str, schema_data: Dict[str, Any]) -> RulebookSchema:
        """
        解析Schema数据
        
        Args:
            schema_id: SchemaID
            schema_data: Schema原始数据
            
        Returns:
            RulebookSchema: 规则书Schema对象
        """
        try:
            # 解析实体定义
            entities = {}
            for entity_id, entity_def in schema_data.get('entities', {}).items():
                entities[entity_id] = self._parse_entity_definition(entity_id, entity_def)
            
            # 解析规则定义
            rules = {}
            for rule_id, rule_def in schema_data.get('rules', {}).items():
                rules[rule_id] = self._parse_rule_definition(rule_id, rule_def)
            
            # 创建Schema对象
            schema = RulebookSchema(
                schema_id=schema_id,
                name=schema_data.get('name', schema_id),
                version=schema_data.get('version', '1.0.0'),
                author=schema_data.get('author', ''),
                description=schema_data.get('description', ''),
                game_system=schema_data.get('game_system', 'dnd_5e'),
                entities=entities,
                rules=rules,
                created_at=datetime.fromisoformat(schema_data.get('created_at')) if 'created_at' in schema_data else None,
                updated_at=datetime.fromisoformat(schema_data.get('updated_at')) if 'updated_at' in schema_data else None,
                is_active=schema_data.get('is_active', False)
            )
            
            return schema
            
        except Exception as e:
            raise ValidationError(f"解析Schema数据失败: {e}")
    
    def _parse_entity_definition(self, entity_id: str, entity_def: Dict[str, Any]) -> EntityDefinition:
        """解析实体定义"""
        # 解析属性定义
        properties = {}
        for prop_name, prop_def in entity_def.get('properties', {}).items():
            properties[prop_name] = PropertyDefinition(
                name=prop_name,
                type=prop_def.get('type', PropertyType.STRING),
                required=prop_def.get('required', True),
                default=prop_def.get('default'),
                description=prop_def.get('description', ''),
                min_value=prop_def.get('min_value'),
                max_value=prop_def.get('max_value'),
                enum_values=prop_def.get('enum_values'),
                validation_regex=prop_def.get('validation_regex')
            )
        
        # 解析关系定义
        relationships = {}
        for rel_name, rel_def in entity_def.get('relationships', {}).items():
            relationships[rel_name] = RelationshipDefinition(
                name=rel_name,
                target_entity_type=rel_def.get('target_entity_type', ''),
                relationship_type=rel_def.get('relationship_type', RelationshipType.ONE_TO_MANY),
                inverse_relationship=rel_def.get('inverse_relationship'),
                properties=rel_def.get('properties')
            )
        
        # 解析验证规则
        validation_rules = entity_def.get('validation_rules', {})
        
        return EntityDefinition(
            entity_type=entity_id,
            label=entity_def.get('label', entity_id),
            plural_label=entity_def.get('plural_label', f"{entity_id}s"),
            properties=properties,
            relationships=relationships,
            validation_rules=validation_rules
        )
    
    def _parse_rule_definition(self, rule_id: str, rule_def: Dict[str, Any]) -> RuleDefinition:
        """解析规则定义"""
        return RuleDefinition(
            name=rule_id,
            type=rule_def.get('type', RuleType.VALIDATION),
            description=rule_def.get('description', ''),
            expression=rule_def.get('expression', ''),
            parameters=rule_def.get('parameters', {}),
            applicable_to=rule_def.get('applicable_to', []),
            validation_rules=rule_def.get('validation_rules', {})
        )
    
    async def _validate_schema(self, schema: RulebookSchema) -> None:
        """
        验证Schema的完整性
        
        Args:
            schema: 规则书Schema对象
            
        Raises:
            ValidationError: Schema验证失败
        """
        errors = []
        
        # 检查必需字段
        if not schema.name or not schema.game_system:
            errors.append("Schema必须包含name和game_system字段")
        
        # 检查实体定义的循环引用
        entity_refs = {entity_id: set() for entity_id in schema.entities.keys()}
        for entity_id, entity_def in schema.entities.items():
            for rel_name, rel_def in entity_def.relationships.items():
                target_type = rel_def.target_entity_type
                if target_type and target_type not in schema.entities:
                    errors.append(f"实体{entity_id}的关系{rel_name}引用了不存在的实体: {target_type}")
        
        if errors:
            raise ValidationError(f"Schema验证失败: {', '.join(errors)}")
        
        logger.debug(f"Schema验证通过: {schema.schema_id}")
    
    async def get_entity_schema(self, entity_type: str) -> EntityDefinition:
        """
        获取指定实体类型的Schema定义
        
        Args:
            entity_type: 实体类型
            
        Returns:
            EntityDefinition: 实体定义对象
            
        Raises:
            ValidationError: 实体类型不存在
        """
        if not self._active_schema_id:
            raise RuntimeError("没有活跃的Schema")
        
        schema = self._schemas_cache.get(self._active_schema_id)
        if not schema:
            raise RuntimeError(f"活跃Schema未缓存: {self._active_schema_id}")
        
        entity_def = schema.entities.get(entity_type)
        if not entity_def:
            raise ValidationError(f"实体类型不存在: {entity_type}")
        
        return entity_def
    
    async def get_entity_properties(self, entity_type: str) -> Dict[str, PropertyDefinition]:
        """
        获取实体类型的属性定义
        
        Args:
            entity_type: 实体类型
            
        Returns:
            Dict[str, PropertyDefinition]: 属性定义字典
        """
        entity_def = await self.get_entity_schema(entity_type)
        return entity_def.properties
    
    async def get_entity_relationships(self, entity_type: str) -> Dict[str, RelationshipDefinition]:
        """
        获取实体类型的关系定义
        
        Args:
            entity_type: 实体类型
            
        Returns:
            Dict[str, RelationshipDefinition]: 关系定义字典
        """
        entity_def = await self.get_entity_schema(entity_type)
        return entity_def.relationships
    
    async def get_rule(self, rule_name: str) -> RuleDefinition:
        """
        获取指定规则的定义
        
        Args:
            rule_name: 规则名称
            
        Returns:
            RuleDefinition: 规则定义对象
            
        Raises:
            ValidationError: 规则不存在
        """
        if not self._active_schema_id:
            raise RuntimeError("没有活跃的Schema")
        
        schema = self._schemas_cache.get(self._active_schema_id)
        if not schema:
            raise RuntimeError(f"活跃Schema未缓存: {self._active_schema_id}")
        
        rule_def = schema.rules.get(rule_name)
        if not rule_def:
            raise ValidationError(f"规则不存在: {rule_name}")
        
        return rule_def
    
    async def list_schemas(self) -> List[Dict[str, Any]]:
        """
        列出所有可用的规则书Schema
        
        Returns:
            List[Dict[str, Any]]: Schema信息列表
        """
        import os
        
        schemas = []
        schema_dir = Path(self.storage_path)
        
        # 扫描目录中的JSON文件
        for schema_file in schema_dir.glob("*.json"):
            try:
                with open(schema_file, 'r', encoding='utf-8') as f:
                    schema_data = json.load(f)
                    
                schemas.append({
                    'schema_id': schema_file.stem,
                    'name': schema_data.get('name', schema_file.stem),
                    'version': schema_data.get('version', '1.0.0'),
                    'author': schema_data.get('author', ''),
                    'game_system': schema_data.get('game_system', ''),
                    'entity_count': len(schema_data.get('entities', {})),
                    'is_active': schema_data.get('is_active', False)
                })
            except Exception as e:
                logger.warning(f"无法读取Schema文件 {schema_file}: {e}")
        
        return schemas
    
    async def set_active_schema(self, schema_id: str) -> None:
        """
        设置活跃的规则书Schema
        
        Args:
            schema_id: Schema ID
        """
        # 加载并缓存Schema
        schema = await self.load_schema(schema_id)
        
        # 设置活跃Schema
        self._active_schema_id = schema_id
        
        # 清除所有Schema缓存（可选，可根据需求调整）
        # 这里只保留当前活跃Schema的缓存
        logger.info(f"设置活跃Schema: {schema_id}")
    
    def get_active_schema_id(self) -> Optional[str]:
        """
        获取当前活跃的Schema ID
        
        Returns:
            str: Schema ID，如果没有活跃Schema则返回None
        """
        return self._active_schema_id
    
    async def validate_entity_data(self, entity_type: str, 
                                  properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证实体数据是否符合Schema
        
        Args:
            entity_type: 实体类型
            properties: 实体属性数据
            
        Returns:
            Dict[str, Any]: 验证结果 {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str]
            }
        """
        try:
            entity_def = await self.get_entity_schema(entity_type)
            errors = []
            warnings = []
            
            # 检查必需属性
            for prop_name, prop_def in entity_def.properties.items():
                if prop_def.required and prop_name not in properties:
                    errors.append(f"缺少必需属性: {prop_name}")
            
            # 检查属性类型
            for prop_name, value in properties.items():
                prop_def = entity_def.properties.get(prop_name)
                if prop_def:
                    type_ok = self._validate_property_type(prop_def, value)
                    if not type_ok:
                        errors.append(f"属性{prop_name}类型错误: {type(value)}")
                    
                    # 验证范围
                    range_ok = self._validate_property_range(prop_def, value)
                    if not range_ok:
                        errors.append(f"属性{prop_name}值超出范围: {value}")
            
            # 应用验证规则
            validation_errors = self._apply_validation_rules(
                entity_type, entity_def.validation_rules, properties
            )
            if validation_errors:
                errors.extend(validation_errors)
            
            return {
                'valid': len(errors) == 0 and len(warnings) == 0,
                'errors': errors,
                'warnings': warnings
            }
            
        except Exception as e:
            logger.error(f"验证实体数据失败: {e}")
            return {
                'valid': False,
                'errors': [f"验证失败: {str(e)}"],
                'warnings': []
            }
    
    def _validate_property_type(self, prop_def: PropertyDefinition, value: Any) -> bool:
        """验证属性类型"""
        if value is None:
            return not prop_def.required
        elif prop_def.type == PropertyType.STRING:
            return isinstance(value, str)
        elif prop_def.type in [PropertyType.INTEGER, PropertyType.NUMBER]:
            return isinstance(value, (int, float))
        elif prop_def.type == PropertyType.BOOLEAN:
            return isinstance(value, bool)
        elif prop_def.type == PropertyType.ARRAY:
            return isinstance(value, list)
        elif prop_def.type == PropertyType.OBJECT:
            return isinstance(value, dict)
        else:
            return True  # 动态类型允许任何类型
    
    def _validate_property_range(self, prop_def: PropertyDefinition, 
                               value: Any) -> bool:
        """验证属性值范围"""
        if value is None:
            return True
        
        try:
            if prop_def.min_value is not None:
                if value < prop_def.min_value:
                    return False
            if prop_def.max_value is not None:
                if value > prop_def.max_value:
                    return False
            return True
        except TypeError:
            return False
    
    def _apply_validation_rules(self, entity_type: str, 
                              rules: Dict[str, Any], 
                              properties: Dict[str, Any]) -> List[str]:
        """应用Schema中的验证规则"""
        errors = []
        
        for rule_name, rule_def in rules.items():
            if rule_def.type != RuleType.VALIDATION:
                continue
                
            # 检查规则是否适用于当前属性
            applicable_props = rule_def.applicable_to or []
            if not any(prop in properties for prop in applicable_props):
                continue
            
            # 应用规则表达式
            try:
                valid = self._evaluate_rule_expression(
                    rule_def.expression, 
                    rule_def.parameters,
                    properties
                )
                if not valid:
                    errors.append(f"验证规则{rule_name}失败")
            except Exception as e:
                errors.append(f"验证规则{rule_name}执行失败: {e}")
        
        return errors
    
    def _evaluate_rule_expression(self, expression: str, 
                               parameters: Dict[str, Any],
                               properties: Dict[str, Any]) -> bool:
        """
        评估规则表达式
        
        这是一个简化的实现，支持基本的数学和逻辑表达式
        对于生产环境，可能需要更强大的表达式引擎
        """
        # 替换表达式中的参数占位符
        expr = expression
        for param_name, param_value in parameters.items():
            expr = expr.replace(f"${{{param_name}}}", str(param_value))
        
        try:
            # 使用eval进行表达式计算
            # 注意：生产环境应该使用更安全的表达式解析器
            result = eval(expr, {"__builtins__": {}})
            return bool(result)
        except Exception as e:
            logger.warning(f"规则表达式评估失败: {expression}, 错误: {e}")
            return False


# 导出函数
__all__ = [
    "SchemaManager",
    "RulebookSchema",
    "EntityDefinition",
    "PropertyDefinition",
    "RelationshipDefinition",
    "RuleDefinition",
    "PropertyType",
    "RelationshipType",
    "RuleType",
]