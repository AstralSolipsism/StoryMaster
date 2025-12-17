"""
实例化管理器实现

负责管理实体原型与实例的关系，支持实例的创建、更新和查询。
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from ..interfaces import (
    IInstantiationManager,
    IStorageAdapter,
    ICacheManager,
    Entity,
    EntityInstance,
    EntityTemplate,
    InstantiationRule,
    InstantiationConfig,
    DataStorageError,
    ValidationError
)

logger = logging.getLogger(__name__)


class InstantiationManager(IInstantiationManager):
    """实例化管理器实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None,
        config: Optional[InstantiationConfig] = None
    ):
        """
        初始化实例化管理器
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器
            config: 实例化配置
        """
        self._storage = storage_adapter
        self._cache = cache_manager
        self._config = config or InstantiationConfig()
        
        # 缓存实例化规则
        self._rules_cache: Dict[str, InstantiationRule] = {}
        
        logger.info("实例化管理器初始化完成")
    
    async def initialize(self) -> None:
        """初始化实例化管理器"""
        try:
            # 加载所有实例化规则
            await self._load_instantiation_rules()
            
            logger.info("实例化管理器初始化成功")
        except Exception as e:
            logger.error(f"实例化管理器初始化失败: {e}")
            raise DataStorageError(f"实例化管理器初始化失败: {e}")
    
    async def _load_instantiation_rules(self) -> None:
        """加载实例化规则"""
        try:
            # 从存储中查询所有实例化规则
            query = """
            MATCH (r:InstantiationRule)
            RETURN r
            """
            
            result = await self._storage.query(query)
            
            for record in result:
                rule_data = record.get('r')
                if rule_data:
                    rule = InstantiationRule(
                        id=rule_data.get('id'),
                        name=rule_data.get('name'),
                        description=rule_data.get('description'),
                        source_type=rule_data.get('source_type'),
                        target_type=rule_data.get('target_type'),
                        conditions=rule_data.get('conditions', {}),
                        transformations=rule_data.get('transformations', {}),
                        constraints=rule_data.get('constraints', {}),
                        priority=rule_data.get('priority', 0),
                        enabled=rule_data.get('enabled', True)
                    )
                    
                    self._rules_cache[rule.id] = rule
            
            logger.info(f"加载了 {len(self._rules_cache)} 个实例化规则")
            
        except Exception as e:
            logger.error(f"加载实例化规则失败: {e}")
            raise
    
    async def create_instance(
        self,
        template_id: str,
        instance_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> EntityInstance:
        """
        创建实体实例
        
        Args:
            template_id: 模板ID
            instance_data: 实例数据
            context: 上下文信息
            
        Returns:
            创建的实体实例
        """
        try:
            # 获取模板
            template = await self._get_template(template_id)
            if not template:
                raise ValidationError(f"模板不存在: {template_id}")
            
            # 验证实例数据
            await self._validate_instance_data(template, instance_data)
            
            # 应用实例化规则
            transformed_data = await self._apply_instantiation_rules(
                template, instance_data, context
            )
            
            # 创建实例 - 使用UUID确保ID唯一性
            import uuid
            instance = EntityInstance(
                id=f"{template.id}_instance_{uuid.uuid4()}",
                template_id=template.id,
                entity_type=template.entity_type,
                properties=transformed_data,
                status="active",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # 保存到存储
            await self._save_instance(instance)
            
            # 缓存实例
            if self._cache:
                await self._cache.set(
                    f"instance:{instance.id}",
                    instance.dict(),
                    ttl=self._config.cache_ttl
                )
            
            logger.info(f"创建实例成功: {instance.id}")
            return instance
            
        except Exception as e:
            logger.error(f"创建实例失败: {e}")
            raise DataStorageError(f"创建实例失败: {e}")
    
    async def get_instance(self, instance_id: str) -> Optional[EntityInstance]:
        """
        获取实体实例
        
        Args:
            instance_id: 实例ID
            
        Returns:
            实体实例或None
        """
        try:
            # 先从缓存获取
            if self._cache:
                cached_data = await self._cache.get(f"instance:{instance_id}")
                if cached_data:
                    return EntityInstance(**cached_data)
            
            # 从存储获取
            query = """
            MATCH (i:EntityInstance {id: $instance_id})
            OPTIONAL MATCH (i)-[:BASED_ON]->(t:EntityTemplate)
            RETURN i, t
            """
            
            result = await self._storage.query(query, {"instance_id": instance_id})
            
            if not result:
                return None
            
            record = result[0]
            instance_data = record.get('i')
            template_data = record.get('t')
            
            instance = EntityInstance(
                id=instance_data.get('id'),
                template_id=instance_data.get('template_id'),
                entity_type=instance_data.get('entity_type'),
                properties=instance_data.get('properties', {}),
                status=instance_data.get('status', 'active'),
                created_at=instance_data.get('created_at'),
                updated_at=instance_data.get('updated_at'),
                template=EntityTemplate(**template_data) if template_data else None
            )
            
            # 缓存实例
            if self._cache:
                await self._cache.set(
                    f"instance:{instance_id}",
                    instance.dict(),
                    ttl=self._config.cache_ttl
                )
            
            return instance
            
        except Exception as e:
            logger.error(f"获取实例失败: {e}")
            raise DataStorageError(f"获取实例失败: {e}")
    
    async def update_instance(
        self,
        instance_id: str,
        updates: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> EntityInstance:
        """
        更新实体实例
        
        Args:
            instance_id: 实例ID
            updates: 更新数据
            context: 上下文信息
            
        Returns:
            更新后的实体实例
        """
        try:
            # 获取现有实例
            instance = await self.get_instance(instance_id)
            if not instance:
                raise ValidationError(f"实例不存在: {instance_id}")
            
            # 获取模板
            template = await self._get_template(instance.template_id)
            if not template:
                raise ValidationError(f"模板不存在: {instance.template_id}")
            
            # 合并更新数据
            updated_properties = {**instance.properties, **updates}
            
            # 验证更新后的数据
            await self._validate_instance_data(template, updated_properties)
            
            # 应用实例化规则
            transformed_data = await self._apply_instantiation_rules(
                template, updated_properties, context
            )
            
            # 更新实例
            instance.properties = transformed_data
            instance.updated_at = datetime.now()
            
            # 保存到存储
            await self._save_instance(instance)
            
            # 更新缓存
            if self._cache:
                await self._cache.set(
                    f"instance:{instance_id}",
                    instance.dict(),
                    ttl=self._config.cache_ttl
                )
            
            logger.info(f"更新实例成功: {instance_id}")
            return instance
            
        except Exception as e:
            logger.error(f"更新实例失败: {e}")
            raise DataStorageError(f"更新实例失败: {e}")
    
    async def delete_instance(self, instance_id: str) -> bool:
        """
        删除实体实例
        
        Args:
            instance_id: 实例ID
            
        Returns:
            是否删除成功
        """
        try:
            # 从存储删除
            query = """
            MATCH (i:EntityInstance {id: $instance_id})
            DETACH DELETE i
            """
            
            await self._storage.execute(query, {"instance_id": instance_id})
            
            # 从缓存删除
            if self._cache:
                await self._cache.delete(f"instance:{instance_id}")
            
            logger.info(f"删除实例成功: {instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除实例失败: {e}")
            return False
    
    async def find_instances(
        self,
        template_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> List[EntityInstance]:
        """
        查找实体实例
        
        Args:
            template_id: 模板ID（可选）
            filters: 过滤条件
            limit: 结果限制
            
        Returns:
            匹配的实例列表
        """
        try:
            # 构建查询
            query_parts = ["MATCH (i:EntityInstance)"]
            
            if template_id:
                query_parts.append("WHERE i.template_id = $template_id")
            
            if filters:
                filter_conditions = []
                for key, value in filters.items():
                    filter_conditions.append(f"i.properties.{key} = ${key}")
                
                if template_id:
                    query_parts.append("AND " + " AND ".join(filter_conditions))
                else:
                    query_parts.append("WHERE " + " AND ".join(filter_conditions))
            
            query_parts.append("RETURN i")
            
            if limit:
                query_parts.append("LIMIT $limit")
            
            query = " ".join(query_parts)
            
            # 准备参数
            params = {"template_id": template_id, **(filters or {})}
            if limit:
                params["limit"] = limit
            
            # 执行查询
            result = await self._storage.query(query, params)
            
            instances = []
            for record in result:
                instance_data = record.get('i')
                if instance_data:
                    instance = EntityInstance(
                        id=instance_data.get('id'),
                        instance_id=instance_data.get('id'),
                        template_id=instance_data.get('template_id'),
                        template_type=instance_data.get('entity_type'),
                        entity_type=instance_data.get('entity_type'),
                        properties=instance_data.get('properties', {}),
                        created_at=instance_data.get('created_at'),
                        updated_at=instance_data.get('updated_at')
                    )
                    instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"查找实例失败: {e}")
            raise DataStorageError(f"查找实例失败: {e}")
    
    async def get_template(self, template_id: str) -> Optional[EntityTemplate]:
        """
        获取实体模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            实体模板或None
        """
        return await self._get_template(template_id)
    
    async def _get_template(self, template_id: str) -> Optional[EntityTemplate]:
        """获取模板的内部实现"""
        try:
            # 先从缓存获取
            if self._cache:
                cached_data = await self._cache.get(f"template:{template_id}")
                if cached_data:
                    return EntityTemplate(**cached_data)
            
            # 从存储获取
            query = """
            MATCH (t:EntityTemplate {id: $template_id})
            RETURN t
            """
            
            result = await self._storage.query(query, {"template_id": template_id})
            
            if not result:
                return None
            
            template_data = result[0].get('t')
            template = EntityTemplate(
                id=template_data.get('id'),
                name=template_data.get('name'),
                description=template_data.get('description'),
                entity_type=template_data.get('entity_type'),
                properties_schema=template_data.get('properties_schema', {}),
                default_properties=template_data.get('default_properties', {}),
                validation_rules=template_data.get('validation_rules', {}),
                created_at=template_data.get('created_at'),
                updated_at=template_data.get('updated_at')
            )
            
            # 缓存模板
            if self._cache:
                await self._cache.set(
                    f"template:{template_id}",
                    template.dict(),
                    ttl=self._config.cache_ttl
                )
            
            return template
            
        except Exception as e:
            logger.error(f"获取模板失败: {e}")
            return None
    
    async def _validate_instance_data(
        self,
        template: EntityTemplate,
        instance_data: Dict[str, Any]
    ) -> None:
        """验证实例数据"""
        try:
            # 检查必需属性
            required_props = template.properties_schema.get('required', [])
            for prop in required_props:
                if prop not in instance_data:
                    raise ValidationError(f"缺少必需属性: {prop}")
            
            # 检查属性类型
            properties = template.properties_schema.get('properties', {})
            for prop_name, prop_schema in properties.items():
                if prop_name in instance_data:
                    expected_type = prop_schema.get('type')
                    actual_value = instance_data[prop_name]
                    
                    # 简单类型检查
                    if expected_type == 'string' and not isinstance(actual_value, str):
                        raise ValidationError(f"属性 {prop_name} 应为字符串类型")
                    elif expected_type == 'number' and not isinstance(actual_value, (int, float)):
                        raise ValidationError(f"属性 {prop_name} 应为数字类型")
                    elif expected_type == 'boolean' and not isinstance(actual_value, bool):
                        raise ValidationError(f"属性 {prop_name} 应为布尔类型")
            
            # 应用验证规则
            validation_rules = template.validation_rules
            if validation_rules:
                # 这里可以实现更复杂的验证逻辑
                pass
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"验证实例数据失败: {e}")
            raise ValidationError(f"验证实例数据失败: {e}")
    
    async def _apply_instantiation_rules(
        self,
        template: EntityTemplate,
        instance_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """应用实例化规则"""
        try:
            transformed_data = instance_data.copy()
            
            # 获取适用的规则
            applicable_rules = [
                rule for rule in self._rules_cache.values()
                if (rule.enabled and 
                    rule.source_type == template.entity_type and
                    self._rule_conditions_met(rule, instance_data, context))
            ]
            
            # 按优先级排序
            applicable_rules.sort(key=lambda r: r.priority, reverse=True)
            
            # 应用规则
            for rule in applicable_rules:
                transformed_data = await self._apply_single_rule(
                    rule, transformed_data, context
                )
            
            return transformed_data
            
        except Exception as e:
            logger.error(f"应用实例化规则失败: {e}")
            return instance_data
    
    def _rule_conditions_met(
        self,
        rule: InstantiationRule,
        instance_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """检查规则条件是否满足"""
        try:
            conditions = rule.conditions
            
            # 检查属性条件
            if 'properties' in conditions:
                for prop_name, expected_value in conditions['properties'].items():
                    if instance_data.get(prop_name) != expected_value:
                        return False
            
            # 检查上下文条件
            if 'context' in conditions and context:
                for key, expected_value in conditions['context'].items():
                    if context.get(key) != expected_value:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查规则条件失败: {e}")
            return False
    
    async def _apply_single_rule(
        self,
        rule: InstantiationRule,
        instance_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """应用单个规则"""
        try:
            transformed_data = instance_data.copy()
            transformations = rule.transformations
            
            # 属性转换
            if 'properties' in transformations:
                for prop_name, transformation in transformations['properties'].items():
                    if transformation['type'] == 'set_value':
                        transformed_data[prop_name] = transformation['value']
                    elif transformation['type'] == 'copy_from':
                        source_prop = transformation['source']
                        if source_prop in transformed_data:
                            transformed_data[prop_name] = transformed_data[source_prop]
                    elif transformation['type'] == 'calculate':
                        # 简单计算示例
                        if transformation['operation'] == 'add':
                            operands = transformation['operands']
                            value = sum(transformed_data.get(op, 0) for op in operands)
                            transformed_data[prop_name] = value
            
            return transformed_data
            
        except Exception as e:
            logger.error(f"应用规则失败: {e}")
            return instance_data
    
    async def _save_instance(self, instance: EntityInstance) -> None:
        """保存实例到存储"""
        try:
            # 创建或更新实例节点
            query = """
            MERGE (i:EntityInstance {id: $id})
            SET i += $properties
            WITH i
            MATCH (t:EntityTemplate {id: $template_id})
            MERGE (i)-[:BASED_ON]->(t)
            """
            
            properties = {
                'id': instance.id,
                'template_id': instance.template_id,
                'entity_type': instance.entity_type,
                'properties': instance.properties,
                'status': instance.status,
                'created_at': instance.created_at.isoformat() if instance.created_at else None,
                'updated_at': instance.updated_at.isoformat() if instance.updated_at else None
            }
            
            params = {
                'id': instance.id,
                'template_id': instance.template_id,
                'properties': properties
            }
            
            await self._storage.execute(query, params)
            
        except Exception as e:
            logger.error(f"保存实例失败: {e}")
            raise DataStorageError(f"保存实例失败: {e}")
    
    async def cleanup(self) -> None:
        """清理资源"""
        try:
            # 清理缓存
            if self._cache:
                # 这里可以实现更精细的缓存清理逻辑
                pass
            
            logger.info("实例化管理器清理完成")
            
        except Exception as e:
            logger.error(f"实例化管理器清理失败: {e}")
    
    async def get_instances_by_template(self, template_id: str) -> List[EntityInstance]:
        """
        获取模板的所有实例
        
        Args:
            template_id: 模板ID
            
        Returns:
            实例列表
        """
        try:
            # 构建查询
            query = """
            MATCH (i:EntityInstance)-[:BASED_ON]->(t:EntityTemplate {id: $template_id})
            RETURN i
            ORDER BY i.created_at DESC
            """
            
            params = {"template_id": template_id}
            
            # 执行查询
            result = await self._storage.query(query, params)
            
            instances = []
            for record in result:
                instance_data = record.get('i')
                if instance_data:
                    instance = EntityInstance(
                        id=instance_data.get('id'),
                        instance_id=instance_data.get('id'),
                        template_id=instance_data.get('template_id'),
                        template_type=instance_data.get('entity_type'),
                        entity_type=instance_data.get('entity_type'),
                        properties=instance_data.get('properties', {}),
                        created_at=instance_data.get('created_at'),
                        updated_at=instance_data.get('updated_at')
                    )
                    instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"获取模板实例失败: {e}")
            raise DataStorageError(f"获取模板实例失败: {e}")