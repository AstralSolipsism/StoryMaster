"""
动态实体工厂

根据规则书Schema动态创建和管理实体，替代硬编码的实体类。
支持运行时实体类型定义、属性验证和关系管理。
"""

import logging
from typing import Dict, List, Optional, Any, Type
from datetime import datetime
from abc import ABC, abstractmethod

from .dynamic_entity import DynamicEntity
from ..core.schema_manager import SchemaManager, RulebookSchema, EntityDefinition
from ..core.exceptions import StoryMasterValidationError as ValidationError
from ..data_storage.interfaces import DataStorageError

logger = logging.getLogger(__name__)


# ==================== 实例化规则系统 ====================

@dataclass
class InstantiationContext:
    """实例化上下文"""
    schema_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    parameters: Dict[str, Any]
    created_at: datetime = None


@dataclass
class InstantiationResult:
    """实例化结果"""
    success: bool
    entity_id: Optional[str] = None
    entity: Optional[DynamicEntity] = None
    errors: List[str]
    warnings: List[str]
    applied_rules: List[str]


class InstantiationRule(ABC):
    """实例化规则基类"""
    
    @property
    @abstractmethod
    def rule_name(self) -> str:
        """规则名称"""
        pass
    
    @abstractmethod
    def apply(self, context: InstantiationContext, entity_def: EntityDefinition, 
                 instance_data: Dict[str, Any]) -> Optional[str]:
        """
        应用规则到实体实例
        
        Args:
            context: 实例化上下文
            entity_def: 实体定义
            instance_data: 实例数据
            
        Returns:
            规则应用结果或None（规则不适用）
        """
        pass
    
    @abstractmethod
    def is_applicable(self, context: InstantiationContext, 
                     entity_def: EntityDefinition) -> bool:
        """
        判断规则是否适用
        
        Args:
            context: 实例化上下文
            entity_def: 实体定义
            
        Returns:
            规则是否适用
        """
        pass


class DefaultValueRule(InstantiationRule):
    """默认值规则"""
    
    @property
    def rule_name(self) -> str:
        return "default_value"
    
    def is_applicable(self, context: InstantiationContext, 
                     entity_def: EntityDefinition) -> bool:
        """默认值规则始终适用"""
        return True
    
    def apply(self, context: InstantiationContext, entity_def: EntityDefinition, 
                 instance_data: Dict[str, Any]) -> Optional[str]:
        """应用默认值规则"""
        properties = entity_def.properties
        errors = []
        
        for prop_name, prop_def in properties.items():
            # 检查是否已提供值
            if prop_name not in instance_data:
                if prop_def.default is not None:
                    instance_data[prop_name] = prop_def.default
                    logger.debug(f"应用默认值: {entity_def.entity_type}.{prop_name} = {prop_def.default}")
                elif prop_def.required:
                    errors.append(f"缺少必需属性: {prop_name}")
        
        return None


class FormulaRule(InstantiationRule):
    """公式计算规则"""
    
    def __init__(self, formula: str, target_property: str):
        self.formula = formula
        self.target_property = target_property
    
    @property
    def rule_name(self) -> str:
        return f"formula:{self.target_property}"
    
    def is_applicable(self, context: InstantiationContext, 
                     entity_def: EntityDefinition) -> bool:
        """检查公式是否可计算"""
        # 检查所有依赖属性是否可用
        dependencies = self._extract_dependencies(self.formula)
        available = all(dep in entity_def.properties for dep in dependencies)
        return available
    
    def apply(self, context: InstantiationContext, entity_def: EntityDefinition, 
                 instance_data: Dict[str, Any]) -> Optional[str]:
        """应用公式计算规则"""
        # 评估公式
        try:
            value = self._evaluate_formula(instance_data)
            instance_data[self.target_property] = value
            logger.debug(f"应用公式规则: {self.formula} = {value}")
            return None
        except Exception as e:
            raise ValidationError(f"公式计算失败: {self.formula}, 错误: {e}")
    
    def _extract_dependencies(self, formula: str) -> List[str]:
        """提取公式中的属性依赖"""
        import re
        # 简单的模式匹配，找到花括号中的属性名
        pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
        dependencies = re.findall(pattern, formula)
        return dependencies
    
    def _evaluate_formula(self, data: Dict[str, Any]) -> Any:
        """安全评估公式"""
        # 构建安全的评估环境
        safe_dict = {
            'max': max,
            'min': min,
            'abs': abs,
            'round': round
        }
        
        try:
            # 替换公式中的属性引用
            expr = self.formula
            for key, value in data.items():
                if value is not None:
                    expr = expr.replace(f'{{{key}}}', str(value))
            
            # 安全评估
            return eval(expr, {"__builtins__": safe_dict})
        except Exception as e:
            logger.warning(f"公式评估失败: {self.formula}, 错误: {e}")
            return None


class ValidationRule(InstantiationRule):
    """数据验证规则"""
    
    def __init__(self, validation_type: str, property_name: str):
        self.validation_type = validation_type
        self.property_name = property_name
    
    @property
    def rule_name(self) -> str:
        return f"validation:{self.validation_type}:{self.property_name}"
    
    def is_applicable(self, context: InstantiationContext, 
                     entity_def: EntityDefinition) -> bool:
        """验证规则始终适用"""
        return True
    
    def apply(self, context: InstantiationContext, entity_def: EntityDefinition, 
                 instance_data: Dict[str, Any]) -> Optional[str]:
        """应用验证规则"""
        if self.property_name not in instance_data:
            raise ValidationError(f"验证属性不存在: {self.property_name}")
        
        value = instance_data[self.property_name]
        errors = []
        
        if self.validation_type == "required":
            if not value:
                errors.append(f"属性{self.property_name}不能为空或None")
        
        elif self.validation_type == "type":
            prop_def = entity_def.properties.get(self.property_name)
            if prop_def:
                type_ok = self._validate_type(value, prop_def.type)
                if not type_ok:
                    errors.append(f"属性{self.property_name}类型错误: {type(value)}, 需要{prop_def.type}")
        
        elif self.validation_type == "range":
            prop_def = entity_def.properties.get(self.property_name)
            if prop_def:
                min_ok = self._validate_min(value, prop_def.min_value)
                max_ok = self._validate_max(value, prop_def.max_value)
                if not min_ok:
                    errors.append(f"属性{self.property_name}值过小: {value} < {prop_def.min_value}")
                if not max_ok:
                    errors.append(f"属性{self.property_name}值过大: {value} > {prop_def.max_value}")
        
        elif self.validation_type == "pattern":
            prop_def = entity_def.properties.get(self.property_name)
            if prop_def and prop_def.validation_regex:
                import re
                if not re.match(prop_def.validation_regex, str(value)):
                    errors.append(f"属性{self.property_name}格式不匹配: {prop_def.validation_regex}")
        
        if errors:
            raise ValidationError(f"验证失败: {', '.join(errors)}")
        
        logger.debug(f"验证通过: {self.validation_type}:{self.property_name}")
        return None
    
    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """验证类型"""
        type_map = {
            'string': str,
            'integer': (int, float),
            'number': (int, float),
            'boolean': bool,
            'array': list,
            'object': dict
        }
        return isinstance(value, type_map.get(expected_type, str))
    
    def _validate_min(self, value: Any, min_value: Any) -> bool:
        """验证最小值"""
        try:
            return float(value) >= float(min_value)
        except (TypeError, ValueError):
            return False
    
    def _validate_max(self, value: Any, max_value: Any) -> bool:
        """验证最大值"""
        try:
            return float(value) <= float(max_value)
        except (TypeError, ValueError):
            return False


class DependencyRule(InstantiationRule):
    """依赖关系规则"""
    
    def __init__(self, depends_on: str, target_property: str):
        self.depends_on = depends_on
        self.target_property = target_property
    
    @property
    def rule_name(self) -> str:
        return f"dependency:{self.depends_on}->{self.target_property}"
    
    def is_applicable(self, context: InstantiationContext, 
                     entity_def: EntityDefinition) -> bool:
        """检查依赖是否存在于实体定义中"""
        # 检查目标属性是否存在
        if self.target_property not in entity_def.properties:
            return False
        
        # 检查依赖属性是否存在
        if self.depends_on not in entity_def.properties:
            return False
        
        return True
    
    def apply(self, context: InstantiationContext, entity_def: EntityDefinition, 
                 instance_data: Dict[str, Any]) -> Optional[str]:
        """应用依赖关系"""
        # 检查依赖属性是否已设置
        if self.depends_on not in instance_data:
            raise ValidationError(f"缺少依赖属性: {self.depends_on}")
        
        # 确保目标属性已正确设置
        if self.target_property in instance_data:
            logger.debug(f"依赖关系满足: {self.depends_on} -> {self.target_property}")
        return None
        
        raise ValidationError(f"目标属性未设置: {self.target_property}")


class RelationshipInstantiationRule(InstantiationRule):
    """关系实例化规则"""
    
    def __init__(self, relationship_name: str):
        self.relationship_name = relationship_name
    
    @property
    def rule_name(self) -> str:
        return f"relationship:{self.relationship_name}"
    
    def is_applicable(self, context: InstantiationContext, 
                     entity_def: EntityDefinition) -> bool:
        """检查实体是否有此关系"""
        return self.relationship_name in entity_def.relationships
    
    def apply(self, context: InstantiationContext, entity_def: EntityDefinition, 
                 instance_data: Dict[str, Any]) -> Optional[str]:
        """应用关系实例化规则"""
        # 在这里不直接创建关系，只是记录需要的关系
        # 实际的关系创建由Repository处理
        logger.debug(f"关系实例化: {self.relationship_name}")
        return None


# ==================== 实体工厂 ====================

class DynamicEntityFactory:
    """动态实体工厂
    
    根据规则书Schema动态创建和管理实体
    """
    
    def __init__(self, schema_manager: SchemaManager):
        """
        初始化动态实体工厂
        
        Args:
            schema_manager: Schema管理器
        """
        self.schema_manager = schema_manager
        self._rule_registry: Dict[str, InstantiationRule] = {}
        self._initialize_default_rules()
    
    def _initialize_default_rules(self) -> None:
        """初始化默认规则"""
        # 注册默认规则
        self._rule_registry = {
            'default_value': DefaultValueRule(),
        }
        
        logger.debug(f"初始化{len(self._rule_registry)}个默认规则")
    
    def register_rule(self, rule: InstantiationRule) -> None:
        """
        注册自定义实例化规则
        
        Args:
            rule: 实例化规则
        """
        self._rule_registry[rule.rule_name] = rule
        logger.info(f"注册实例化规则: {rule.rule_name}")
    
    def unregister_rule(self, rule_name: str) -> None:
        """
        注销实例化规则
        
        Args:
            rule_name: 规则名称
        """
        if rule_name in self._rule_registry:
            del self._rule_registry[rule_name]
            logger.info(f"注销实例化规则: {rule_name}")
    
    async def create_entity(self, entity_type: str, context: InstantiationContext) -> InstantiationResult:
        """
        创建动态实体实例
        
        Args:
            entity_type: 实体类型
            context: 实例化上下文
            
        Returns:
            InstantiationResult: 实例化结果
        """
        try:
            # 获取实体Schema
            entity_def = await self.schema_manager.get_entity_schema(entity_type)
            
            # 创建空的实例数据
            instance_data = {
                'id': f"{entity_type}_{datetime.now().timestamp()}",
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # 应用实例化规则
            applied_rules = []
            errors = []
            warnings = []
            
            for rule_name, rule in self._rule_registry.items():
                if rule.is_applicable(context, entity_def):
                    try:
                        rule.apply(context, entity_def, instance_data)
                        applied_rules.append(rule_name)
                    except ValidationError as e:
                        errors.append(str(e))
                    except Exception as e:
                        warnings.append(f"规则{rule_name}执行警告: {e}")
            
            # 如果提供了初始数据，应用到实例
            if context.parameters:
                for key, value in context.parameters.items():
                    if key in entity_def.properties:
                        instance_data[key] = value
            
            # 创建动态实体
            entity = DynamicEntity(entity_type, entity_def)
            
            # 批量设置属性
            for prop_name, prop_value in instance_data.items():
                if prop_name != 'id':  # ID已设置
                    entity.set_property(prop_name, prop_value, validate=False)
            
            # 验证实体
            validation_result = entity.validate()
            if not validation_result['valid']:
                errors.extend(validation_result['errors'])
            
            return InstantiationResult(
                success=len(errors) == 0,
                entity_id=entity.id,
                entity=entity if len(errors) == 0 else None,
                errors=errors,
                warnings=warnings,
                applied_rules=applied_rules
            )
            
        except Exception as e:
            logger.error(f"创建实体失败: {entity_type}, 错误: {e}")
            return InstantiationResult(
                success=False,
                errors=[str(e)],
                warnings=[],
                applied_rules=[]
            )
    
    async def create_entity_from_template(self, entity_type: str, template_id: str,
                                       instance_data: Dict[str, Any],
                                       context: InstantiationContext) -> InstantiationResult:
        """
        基于模板创建实体实例
        
        Args:
            entity_type: 实体类型
            template_id: 模板ID
            instance_data: 实例数据
            context: 实例化上下文
            
        Returns:
            InstantiationResult: 实例化结果
        """
        try:
            # 获取模板和目标类型Schema
            template_entity_def = await self.schema_manager.get_entity_schema(template_id)
            target_entity_def = await self.schema_manager.get_entity_schema(entity_type)
            
            if not template_entity_def or not target_entity_def:
                raise ValidationError(f"模板或目标实体类型不存在")
            
            # 合并模板属性和实例数据
            merged_data = {}
            
            # 复制模板的默认属性
            for prop_name, prop_def in template_entity_def.properties.items():
                if prop_name not in instance_data:
                    if prop_def.default is not None:
                        merged_data[prop_name] = prop_def.default
            
            # 覆盖实例数据
            merged_data.update(instance_data)
            
            # 设置模板引用
            merged_data['_template_id'] = template_id
            merged_data['_template_type'] = template_entity_def.entity_type
            
            # 创建实例化上下文
            creation_context = InstantiationContext(
                schema_id=target_entity_def.schema_id or template_entity_def.schema_id,
                user_id=context.user_id,
                session_id=context.session_id,
                parameters=merged_data
            )
            
            return await self.create_entity(entity_type, creation_context)
            
        except Exception as e:
            logger.error(f"从模板创建实例失败: {template_id} -> {entity_type}, 错误: {e}")
            return InstantiationResult(
                success=False,
                errors=[str(e)],
                warnings=[],
                applied_rules=[]
            )
    
    async def batch_create_entities(self, entities: List[Dict[str, Any]], 
                             entity_type: str) -> List[InstantiationResult]:
        """
        批量创建实体
        
        Args:
            entities: 实体数据列表
            entity_type: 实体类型
            
        Returns:
            实例化结果列表
        """
        results = []
        
        for entity_data in entities:
            context = InstantiationContext(
                schema_id=entity_data.get('schema_id'),
                user_id=entity_data.get('user_id'),
                parameters=entity_data
            )
            
            result = await self.create_entity(entity_type, context)
            results.append(result)
        
        success_count = sum(1 for r in results if r.success)
        logger.info(f"批量创建完成: {success_count}/{len(results)} 成功")
        
        return results
    
    def get_registered_rules(self) -> Dict[str, InstantiationRule]:
        """获取所有注册的规则"""
        return self._rule_registry.copy()
    
    async def validate_entity_data(self, entity_type: str, 
                              data: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证实体数据
        
        Args:
            entity_type: 实体类型
            data: 实体数据
            
        Returns:
            验证结果
        """
        try:
            entity_def = await self.schema_manager.get_entity_schema(entity_type)
            
            # 创建临时实体进行验证
            entity = DynamicEntity(entity_type, entity_def)
            
            # 设置属性进行验证
            for prop_name, value in data.items():
                if prop_name in entity_def.properties:
                    entity.set_property(prop_name, value, validate=False)
            
            # 验证实体
            validation_result = entity.validate()
            
            return validation_result
            
        except Exception as e:
            return {
                'valid': False,
                'errors': [f"验证失败: {str(e)}"],
                'warnings': []
            }


# 导出函数
__all__ = [
    "InstantiationContext",
    "InstantiationResult",
    "InstantiationRule",
    "DefaultValueRule",
    "FormulaRule",
    "ValidationRule",
    "DependencyRule",
    "RelationshipInstantiationRule",
    "DynamicEntityFactory",
]