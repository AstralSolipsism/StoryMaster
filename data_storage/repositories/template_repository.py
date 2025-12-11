"""
模板仓库实现

提供实体模板的数据访问操作，包括CRUD操作和复杂查询。
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from ..interfaces import (
    ITemplateRepository,
    IStorageAdapter,
    ICacheManager,
    EntityTemplate,
    TemplateFilter,
    QueryResult,
    DataStorageError,
    ValidationError
)

logger = logging.getLogger(__name__)


class TemplateRepository(ITemplateRepository):
    """模板仓库实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ):
        """
        初始化模板仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器
        """
        self._storage = storage_adapter
        self._cache = cache_manager
        
        logger.info("模板仓库初始化完成")
    
    async def create(self, template: EntityTemplate) -> EntityTemplate:
        """
        创建模板
        
        Args:
            template: 模板对象
            
        Returns:
            创建的模板
        """
        try:
            # 验证模板
            await self._validate_template(template)
            
            # 检查是否已存在
            existing = await self.get_by_id(template.id)
            if existing:
                raise ValidationError(f"模板已存在: {template.id}")
            
            # 创建模板节点
            query = """
            CREATE (t:EntityTemplate {
                id: $id,
                name: $name,
                description: $description,
                entity_type: $entity_type,
                properties_schema: $properties_schema,
                default_properties: $default_properties,
                validation_rules: $validation_rules,
                created_at: $created_at,
                updated_at: $updated_at
            })
            RETURN t
            """
            
            params = {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'entity_type': template.entity_type,
                'properties_schema': template.properties_schema,
                'default_properties': template.default_properties,
                'validation_rules': template.validation_rules,
                'created_at': template.created_at.isoformat() if template.created_at else datetime.now().isoformat(),
                'updated_at': template.updated_at.isoformat() if template.updated_at else datetime.now().isoformat()
            }
            
            result = await self._storage.query(query, params)
            
            if not result:
                raise DataStorageError("创建模板失败")
            
            # 缓存模板
            if self._cache:
                await self._cache.set(
                    f"template:{template.id}",
                    template.dict(),
                    ttl=3600  # 1小时
                )
            
            logger.info(f"创建模板成功: {template.id}")
            return template
            
        except Exception as e:
            logger.error(f"创建模板失败: {e}")
            raise DataStorageError(f"创建模板失败: {e}")
    
    async def get_by_id(self, template_id: str) -> Optional[EntityTemplate]:
        """
        根据ID获取模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            模板对象或None
        """
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
                created_at=self._parse_datetime(template_data.get('created_at')),
                updated_at=self._parse_datetime(template_data.get('updated_at'))
            )
            
            # 缓存模板
            if self._cache:
                await self._cache.set(
                    f"template:{template_id}",
                    template.dict(),
                    ttl=3600
                )
            
            return template
            
        except Exception as e:
            logger.error(f"获取模板失败: {e}")
            raise DataStorageError(f"获取模板失败: {e}")
    
    async def update(self, template: EntityTemplate) -> EntityTemplate:
        """
        更新模板
        
        Args:
            template: 模板对象
            
        Returns:
            更新后的模板
        """
        try:
            # 验证模板
            await self._validate_template(template)
            
            # 检查是否存在
            existing = await self.get_by_id(template.id)
            if not existing:
                raise ValidationError(f"模板不存在: {template.id}")
            
            # 更新模板
            query = """
            MATCH (t:EntityTemplate {id: $id})
            SET t.name = $name,
                t.description = $description,
                t.entity_type = $entity_type,
                t.properties_schema = $properties_schema,
                t.default_properties = $default_properties,
                t.validation_rules = $validation_rules,
                t.updated_at = $updated_at
            RETURN t
            """
            
            params = {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'entity_type': template.entity_type,
                'properties_schema': template.properties_schema,
                'default_properties': template.default_properties,
                'validation_rules': template.validation_rules,
                'updated_at': datetime.now().isoformat()
            }
            
            result = await self._storage.query(query, params)
            
            if not result:
                raise DataStorageError("更新模板失败")
            
            # 更新缓存
            if self._cache:
                await self._cache.set(
                    f"template:{template.id}",
                    template.dict(),
                    ttl=3600
                )
            
            logger.info(f"更新模板成功: {template.id}")
            return template
            
        except Exception as e:
            logger.error(f"更新模板失败: {e}")
            raise DataStorageError(f"更新模板失败: {e}")
    
    async def delete(self, template_id: str) -> bool:
        """
        删除模板
        
        Args:
            template_id: 模板ID
            
        Returns:
            是否删除成功
        """
        try:
            # 检查是否有实例使用此模板
            instances_query = """
            MATCH (i:EntityInstance {template_id: $template_id})
            RETURN count(i) as instance_count
            """
            
            instances_result = await self._storage.query(instances_query, {"template_id": template_id})
            instance_count = instances_result[0].get('instance_count', 0) if instances_result else 0
            
            if instance_count > 0:
                raise ValidationError(f"无法删除模板，仍有 {instance_count} 个实例使用此模板")
            
            # 删除模板
            query = """
            MATCH (t:EntityTemplate {id: $template_id})
            DETACH DELETE t
            """
            
            await self._storage.execute(query, {"template_id": template_id})
            
            # 从缓存删除
            if self._cache:
                await self._cache.delete(f"template:{template_id}")
            
            logger.info(f"删除模板成功: {template_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除模板失败: {e}")
            return False
    
    async def find(self, filters: TemplateFilter) -> QueryResult:
        """
        查找模板
        
        Args:
            filters: 过滤条件
            
        Returns:
            查询结果
        """
        try:
            # 构建查询
            query_parts = ["MATCH (t:EntityTemplate)"]
            where_conditions = []
            params = {}
            
            # 添加过滤条件
            if filters.entity_types:
                where_conditions.append("t.entity_type IN $entity_types")
                params['entity_types'] = filters.entity_types
            
            if filters.name_pattern:
                where_conditions.append("t.name CONTAINS $name_pattern")
                params['name_pattern'] = filters.name_pattern
            
            if filters.description_pattern:
                where_conditions.append("t.description CONTAINS $description_pattern")
                params['description_pattern'] = filters.description_pattern
            
            if filters.created_after:
                where_conditions.append("t.created_at >= $created_after")
                params['created_after'] = filters.created_after.isoformat()
            
            if filters.created_before:
                where_conditions.append("t.created_at <= $created_before")
                params['created_before'] = filters.created_before.isoformat()
            
            # 添加WHERE子句
            if where_conditions:
                query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            # 添加排序
            if filters.order_by:
                order_direction = "DESC" if filters.order_desc else "ASC"
                query_parts.append(f"ORDER BY t.{filters.order_by} {order_direction}")
            
            # 添加分页
            if filters.limit:
                query_parts.append(f"LIMIT {filters.limit}")
            
            if filters.offset:
                query_parts.append(f"SKIP {filters.offset}")
            
            query = " ".join(query_parts) + " RETURN t"
            
            # 执行查询
            result = await self._storage.query(query, params)
            
            # 转换结果
            templates = []
            for record in result:
                template_data = record.get('t')
                if template_data:
                    template = EntityTemplate(
                        id=template_data.get('id'),
                        name=template_data.get('name'),
                        description=template_data.get('description'),
                        entity_type=template_data.get('entity_type'),
                        properties_schema=template_data.get('properties_schema', {}),
                        default_properties=template_data.get('default_properties', {}),
                        validation_rules=template_data.get('validation_rules', {}),
                        created_at=self._parse_datetime(template_data.get('created_at')),
                        updated_at=self._parse_datetime(template_data.get('updated_at'))
                    )
                    templates.append(template)
            
            # 获取总数
            count_query = "MATCH (t:EntityTemplate"
            if where_conditions:
                count_query += " WHERE " + " AND ".join(where_conditions)
            count_query += ") RETURN count(t) as total"
            
            count_result = await self._storage.query(count_query, params)
            total_count = count_result[0].get('total', 0) if count_result else 0
            
            return QueryResult(
                items=templates,
                total_count=total_count,
                has_more=(filters.offset or 0) + len(templates) < total_count
            )
            
        except Exception as e:
            logger.error(f"查找模板失败: {e}")
            raise DataStorageError(f"查找模板失败: {e}")
    
    async def find_by_entity_type(self, entity_type: str) -> List[EntityTemplate]:
        """
        根据实体类型查找模板
        
        Args:
            entity_type: 实体类型
            
        Returns:
            模板列表
        """
        try:
            query = """
            MATCH (t:EntityTemplate {entity_type: $entity_type})
            RETURN t
            """
            
            result = await self._storage.query(query, {"entity_type": entity_type})
            
            templates = []
            for record in result:
                template_data = record.get('t')
                if template_data:
                    template = EntityTemplate(
                        id=template_data.get('id'),
                        name=template_data.get('name'),
                        description=template_data.get('description'),
                        entity_type=template_data.get('entity_type'),
                        properties_schema=template_data.get('properties_schema', {}),
                        default_properties=template_data.get('default_properties', {}),
                        validation_rules=template_data.get('validation_rules', {}),
                        created_at=self._parse_datetime(template_data.get('created_at')),
                        updated_at=self._parse_datetime(template_data.get('updated_at'))
                    )
                    templates.append(template)
            
            return templates
            
        except Exception as e:
            logger.error(f"根据实体类型查找模板失败: {e}")
            raise DataStorageError(f"根据实体类型查找模板失败: {e}")
    
    async def find_by_name(self, name: str) -> List[EntityTemplate]:
        """
        根据名称查找模板
        
        Args:
            name: 模板名称
            
        Returns:
            模板列表
        """
        try:
            query = """
            MATCH (t:EntityTemplate {name: $name})
            RETURN t
            """
            
            result = await self._storage.query(query, {"name": name})
            
            templates = []
            for record in result:
                template_data = record.get('t')
                if template_data:
                    template = EntityTemplate(
                        id=template_data.get('id'),
                        name=template_data.get('name'),
                        description=template_data.get('description'),
                        entity_type=template_data.get('entity_type'),
                        properties_schema=template_data.get('properties_schema', {}),
                        default_properties=template_data.get('default_properties', {}),
                        validation_rules=template_data.get('validation_rules', {}),
                        created_at=self._parse_datetime(template_data.get('created_at')),
                        updated_at=self._parse_datetime(template_data.get('updated_at'))
                    )
                    templates.append(template)
            
            return templates
            
        except Exception as e:
            logger.error(f"根据名称查找模板失败: {e}")
            raise DataStorageError(f"根据名称查找模板失败: {e}")
    
    async def search(self, search_term: str, limit: int = 10) -> List[EntityTemplate]:
        """
        搜索模板
        
        Args:
            search_term: 搜索词
            limit: 结果限制
            
        Returns:
            匹配的模板列表
        """
        try:
            query = """
            MATCH (t:EntityTemplate)
            WHERE t.name CONTAINS $search_term 
               OR t.description CONTAINS $search_term
            RETURN t
            LIMIT $limit
            """
            
            params = {
                'search_term': search_term,
                'limit': limit
            }
            
            result = await self._storage.query(query, params)
            
            templates = []
            for record in result:
                template_data = record.get('t')
                if template_data:
                    template = EntityTemplate(
                        id=template_data.get('id'),
                        name=template_data.get('name'),
                        description=template_data.get('description'),
                        entity_type=template_data.get('entity_type'),
                        properties_schema=template_data.get('properties_schema', {}),
                        default_properties=template_data.get('default_properties', {}),
                        validation_rules=template_data.get('validation_rules', {}),
                        created_at=self._parse_datetime(template_data.get('created_at')),
                        updated_at=self._parse_datetime(template_data.get('updated_at'))
                    )
                    templates.append(template)
            
            return templates
            
        except Exception as e:
            logger.error(f"搜索模板失败: {e}")
            raise DataStorageError(f"搜索模板失败: {e}")
    
    async def count(self, filters: Optional[TemplateFilter] = None) -> int:
        """
        统计模板数量
        
        Args:
            filters: 过滤条件（可选）
            
        Returns:
            模板数量
        """
        try:
            query_parts = ["MATCH (t:EntityTemplate)"]
            params = {}
            
            if filters:
                where_conditions = []
                
                if filters.entity_types:
                    where_conditions.append("t.entity_type IN $entity_types")
                    params['entity_types'] = filters.entity_types
                
                if filters.name_pattern:
                    where_conditions.append("t.name CONTAINS $name_pattern")
                    params['name_pattern'] = filters.name_pattern
                
                if filters.description_pattern:
                    where_conditions.append("t.description CONTAINS $description_pattern")
                    params['description_pattern'] = filters.description_pattern
                
                if where_conditions:
                    query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            query_parts.append("RETURN count(t) as total")
            query = " ".join(query_parts)
            
            result = await self._storage.query(query, params)
            
            return result[0].get('total', 0) if result else 0
            
        except Exception as e:
            logger.error(f"统计模板数量失败: {e}")
            raise DataStorageError(f"统计模板数量失败: {e}")
    
    async def get_instance_count(self, template_id: str) -> int:
        """
        获取使用指定模板的实例数量
        
        Args:
            template_id: 模板ID
            
        Returns:
            实例数量
        """
        try:
            query = """
            MATCH (i:EntityInstance {template_id: $template_id})
            RETURN count(i) as instance_count
            """
            
            result = await self._storage.query(query, {"template_id": template_id})
            
            return result[0].get('instance_count', 0) if result else 0
            
        except Exception as e:
            logger.error(f"获取模板实例数量失败: {e}")
            raise DataStorageError(f"获取模板实例数量失败: {e}")
    
    async def _validate_template(self, template: EntityTemplate) -> None:
        """验证模板数据"""
        if not template.id:
            raise ValidationError("模板ID不能为空")
        
        if not template.name:
            raise ValidationError("模板名称不能为空")
        
        if not template.entity_type:
            raise ValidationError("实体类型不能为空")
        
        # 验证属性模式
        if not isinstance(template.properties_schema, dict):
            raise ValidationError("属性模式必须是字典类型")
        
        # 验证默认属性
        if not isinstance(template.default_properties, dict):
            raise ValidationError("默认属性必须是字典类型")
        
        # 验证验证规则
        if not isinstance(template.validation_rules, dict):
            raise ValidationError("验证规则必须是字典类型")
    
    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """解析日期时间字符串"""
        if not datetime_str:
            return None
        
        try:
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None