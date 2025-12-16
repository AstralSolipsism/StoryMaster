"""
实例仓库实现

提供实体实例的数据访问操作，包括CRUD操作和复杂查询。
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from ..interfaces import (
    IInstanceRepository,
    IStorageAdapter,
    ICacheManager,
    EntityInstance,
    InstanceFilter,
    QueryResult,
    DataStorageError,
    ValidationError,
    EntityTemplate
)

logger = logging.getLogger(__name__)


class InstanceRepository(IInstanceRepository):
    """实例仓库实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ):
        """
        初始化实例仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器
        """
        self._storage = storage_adapter
        self._cache = cache_manager
        
        logger.info("实例仓库初始化完成")
    
    async def create(self, instance: EntityInstance) -> EntityInstance:
        """
        创建实例
        
        Args:
            instance: 实例对象
            
        Returns:
            创建的实例
        """
        try:
            # 验证实例
            await self._validate_instance(instance)
            
            # 检查是否已存在
            existing = await self.get_by_id(instance.id)
            if existing:
                raise ValidationError(f"实例已存在: {instance.id}")
            
            # 检查模板是否存在
            template_query = """
            MATCH (t:EntityTemplate {id: $template_id})
            RETURN t
            """
            
            template_result = await self._storage.query(
                template_query, 
                {"template_id": instance.template_id}
            )
            
            if not template_result:
                raise ValidationError(f"模板不存在: {instance.template_id}")
            
            # 创建实例节点
            query = """
            MATCH (t:EntityTemplate {id: $template_id})
            CREATE (i:EntityInstance {
                id: $id,
                template_id: $template_id,
                entity_type: $entity_type,
                properties: $properties,
                status: $status,
                created_at: $created_at,
                updated_at: $updated_at
            })
            CREATE (i)-[:BASED_ON]->(t)
            RETURN i
            """
            
            params = {
                'template_id': instance.template_id,
                'id': instance.id,
                'entity_type': instance.entity_type,
                'properties': instance.properties,
                'status': instance.status,
                'created_at': instance.created_at.isoformat() if instance.created_at else datetime.now().isoformat(),
                'updated_at': instance.updated_at.isoformat() if instance.updated_at else datetime.now().isoformat()
            }
            
            result = await self._storage.query(query, params)
            
            if not result:
                raise DataStorageError("创建实例失败")
            
            # 缓存实例
            if self._cache:
                await self._cache.set(
                    f"instance:{instance.id}",
                    instance.dict(),
                    ttl=3600  # 1小时
                )
            
            logger.info(f"创建实例成功: {instance.id}")
            return instance
            
        except Exception as e:
            logger.error(f"创建实例失败: {e}")
            raise DataStorageError(f"创建实例失败: {e}")
    
    async def get_by_id(self, instance_id: str) -> Optional[EntityInstance]:
        """
        根据ID获取实例
        
        Args:
            instance_id: 实例ID
            
        Returns:
            实例对象或None
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
                created_at=self._parse_datetime(instance_data.get('created_at')),
                updated_at=self._parse_datetime(instance_data.get('updated_at')),
                template=self._create_template_from_data(template_data) if template_data else None
            )
            
            # 缓存实例
            if self._cache:
                await self._cache.set(
                    f"instance:{instance_id}",
                    instance.dict(),
                    ttl=3600
                )
            
            return instance
            
        except Exception as e:
            logger.error(f"获取实例失败: {e}")
            raise DataStorageError(f"获取实例失败: {e}")
    
    async def update(self, instance: EntityInstance) -> EntityInstance:
        """
        更新实例
        
        Args:
            instance: 实例对象
            
        Returns:
            更新后的实例
        """
        try:
            # 验证实例
            await self._validate_instance(instance)
            
            # 检查是否存在
            existing = await self.get_by_id(instance.id)
            if not existing:
                raise ValidationError(f"实例不存在: {instance.id}")
            
            # 更新实例
            query = """
            MATCH (i:EntityInstance {id: $id})
            SET i.properties = $properties,
                i.status = $status,
                i.updated_at = $updated_at
            RETURN i
            """
            
            params = {
                'id': instance.id,
                'properties': instance.properties,
                'status': instance.status,
                'updated_at': datetime.now().isoformat()
            }
            
            result = await self._storage.query(query, params)
            
            if not result:
                raise DataStorageError("更新实例失败")
            
            # 更新缓存
            if self._cache:
                await self._cache.set(
                    f"instance:{instance.id}",
                    instance.dict(),
                    ttl=3600
                )
            
            logger.info(f"更新实例成功: {instance.id}")
            return instance
            
        except Exception as e:
            logger.error(f"更新实例失败: {e}")
            raise DataStorageError(f"更新实例失败: {e}")
    
    async def delete(self, instance_id: str) -> bool:
        """
        删除实例
        
        Args:
            instance_id: 实例ID
            
        Returns:
            是否删除成功
        """
        try:
            # 删除实例及其关系
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
            
        except (ConnectionError, TimeoutError) as e:
            # 系统级错误：数据库连接问题、超时等
            logger.error(f"删除实例时发生系统错误: {e}")
            # 重新抛出系统错误，让上层处理
            raise DataStorageError(f"删除实例时发生系统错误: {e}") from e
        except ValidationError as e:
            # 业务逻辑错误：实例不存在、参数无效等
            logger.warning(f"删除实例失败（业务逻辑）: {e}")
            return False
        except Exception as e:
            # 其他未预期的异常
            logger.error(f"删除实例时发生未预期错误: {e}")
            # 可以重新抛出或根据业务需求处理
            raise
    
    async def find(self, filters: InstanceFilter) -> QueryResult:
        """
        查找实例
        
        Args:
            filters: 过滤条件
            
        Returns:
            查询结果
        """
        try:
            # 构建查询
            query_parts = ["MATCH (i:EntityInstance)"]
            where_conditions = []
            params = {}
            
            # 添加过滤条件
            if filters.template_ids:
                where_conditions.append("i.template_id IN $template_ids")
                params['template_ids'] = filters.template_ids
            
            if filters.entity_types:
                where_conditions.append("i.entity_type IN $entity_types")
                params['entity_types'] = filters.entity_types
            
            if filters.statuses:
                where_conditions.append("i.status IN $statuses")
                params['statuses'] = filters.statuses
            
            if filters.property_filters:
                # 验证属性名，防止注入攻击
                allowed_props = ['name', 'description', 'status', 'entity_type']  # 预定义允许的属性
                for prop_name, prop_value in filters.property_filters.items():
                    if prop_name not in allowed_props:
                        raise ValueError(f"不允许的属性过滤: {prop_name}")
                    
                    where_conditions.append(f"i.properties.{prop_name} = $prop_{prop_name}")
                    params[f'prop_{prop_name}'] = prop_value
            
            if filters.created_after:
                where_conditions.append("i.created_at >= $created_after")
                params['created_after'] = filters.created_after.isoformat()
            
            if filters.created_before:
                where_conditions.append("i.created_at <= $created_before")
                params['created_before'] = filters.created_before.isoformat()
            
            # 添加WHERE子句
            if where_conditions:
                query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            # 添加排序
            if filters.order_by:
                order_direction = "DESC" if filters.order_desc else "ASC"
                query_parts.append(f"ORDER BY i.{filters.order_by} {order_direction}")
            
            # 添加分页 - 使用参数化查询防止SQL注入
            if filters.limit:
                query_parts.append("LIMIT $limit")
                params['limit'] = filters.limit
            
            if filters.offset:
                query_parts.append("SKIP $offset")
                params['offset'] = filters.offset
            
            query = " ".join(query_parts) + " RETURN i"
            
            # 执行查询
            result = await self._storage.query(query, params)
            
            # 转换结果
            instances = []
            for record in result:
                instance_data = record.get('i')
                if instance_data:
                    instance = EntityInstance(
                        id=instance_data.get('id'),
                        template_id=instance_data.get('template_id'),
                        entity_type=instance_data.get('entity_type'),
                        properties=instance_data.get('properties', {}),
                        status=instance_data.get('status', 'active'),
                        created_at=self._parse_datetime(instance_data.get('created_at')),
                        updated_at=self._parse_datetime(instance_data.get('updated_at'))
                    )
                    instances.append(instance)
            
            # 获取总数
            count_query = "MATCH (i:EntityInstance"
            if where_conditions:
                count_query += " WHERE " + " AND ".join(where_conditions)
            count_query += ") RETURN count(i) as total"
            
            count_result = await self._storage.query(count_query, params)
            total_count = count_result[0].get('total', 0) if count_result else 0
            
            return QueryResult(
                items=instances,
                total_count=total_count,
                has_more=(filters.offset or 0) + len(instances) < total_count
            )
            
        except Exception as e:
            logger.error(f"查找实例失败: {e}")
            raise DataStorageError(f"查找实例失败: {e}")
    
    async def find_by_template(self, template_id: str) -> List[EntityInstance]:
        """
        根据模板查找实例
        
        Args:
            template_id: 模板ID
            
        Returns:
            实例列表
        """
        try:
            query = """
            MATCH (i:EntityInstance {template_id: $template_id})
            RETURN i
            """
            
            result = await self._storage.query(query, {"template_id": template_id})
            
            instances = []
            for record in result:
                instance_data = record.get('i')
                if instance_data:
                    instance = EntityInstance(
                        id=instance_data.get('id'),
                        template_id=instance_data.get('template_id'),
                        entity_type=instance_data.get('entity_type'),
                        properties=instance_data.get('properties', {}),
                        status=instance_data.get('status', 'active'),
                        created_at=self._parse_datetime(instance_data.get('created_at')),
                        updated_at=self._parse_datetime(instance_data.get('updated_at'))
                    )
                    instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"根据模板查找实例失败: {e}")
            raise DataStorageError(f"根据模板查找实例失败: {e}")
    
    async def find_by_type(self, entity_type: str) -> List[EntityInstance]:
        """
        根据实体类型查找实例
        
        Args:
            entity_type: 实体类型
            
        Returns:
            实例列表
        """
        try:
            query = """
            MATCH (i:EntityInstance {entity_type: $entity_type})
            RETURN i
            """
            
            result = await self._storage.query(query, {"entity_type": entity_type})
            
            instances = []
            for record in result:
                instance_data = record.get('i')
                if instance_data:
                    instance = EntityInstance(
                        id=instance_data.get('id'),
                        template_id=instance_data.get('template_id'),
                        entity_type=instance_data.get('entity_type'),
                        properties=instance_data.get('properties', {}),
                        status=instance_data.get('status', 'active'),
                        created_at=self._parse_datetime(instance_data.get('created_at')),
                        updated_at=self._parse_datetime(instance_data.get('updated_at'))
                    )
                    instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"根据实体类型查找实例失败: {e}")
            raise DataStorageError(f"根据实体类型查找实例失败: {e}")
    
    async def find_by_status(self, status: str) -> List[EntityInstance]:
        """
        根据状态查找实例
        
        Args:
            status: 实例状态
            
        Returns:
            实例列表
        """
        try:
            query = """
            MATCH (i:EntityInstance {status: $status})
            RETURN i
            """
            
            result = await self._storage.query(query, {"status": status})
            
            instances = []
            for record in result:
                instance_data = record.get('i')
                if instance_data:
                    instance = EntityInstance(
                        id=instance_data.get('id'),
                        template_id=instance_data.get('template_id'),
                        entity_type=instance_data.get('entity_type'),
                        properties=instance_data.get('properties', {}),
                        status=instance_data.get('status', 'active'),
                        created_at=self._parse_datetime(instance_data.get('created_at')),
                        updated_at=self._parse_datetime(instance_data.get('updated_at'))
                    )
                    instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"根据状态查找实例失败: {e}")
            raise DataStorageError(f"根据状态查找实例失败: {e}")
    
    async def search(self, search_term: str, limit: int = 10) -> List[EntityInstance]:
        """
        搜索实例
        
        Args:
            search_term: 搜索词
            limit: 结果限制
            
        Returns:
            匹配的实例列表
        """
        try:
            query = """
            MATCH (i:EntityInstance)
            WHERE any(key in keys(i.properties) 
                   WHERE toString(i.properties[key]) CONTAINS $search_term)
            RETURN i
            LIMIT $limit
            """
            
            params = {
                'search_term': search_term,
                'limit': limit
            }
            
            result = await self._storage.query(query, params)
            
            instances = []
            for record in result:
                instance_data = record.get('i')
                if instance_data:
                    instance = EntityInstance(
                        id=instance_data.get('id'),
                        template_id=instance_data.get('template_id'),
                        entity_type=instance_data.get('entity_type'),
                        properties=instance_data.get('properties', {}),
                        status=instance_data.get('status', 'active'),
                        created_at=self._parse_datetime(instance_data.get('created_at')),
                        updated_at=self._parse_datetime(instance_data.get('updated_at'))
                    )
                    instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"搜索实例失败: {e}")
            raise DataStorageError(f"搜索实例失败: {e}")
    
    async def count(self, filters: Optional[InstanceFilter] = None) -> int:
        """
        统计实例数量
        
        Args:
            filters: 过滤条件（可选）
            
        Returns:
            实例数量
        """
        try:
            query_parts = ["MATCH (i:EntityInstance)"]
            params = {}
            
            if filters:
                where_conditions = []
                
                if filters.template_ids:
                    where_conditions.append("i.template_id IN $template_ids")
                    params['template_ids'] = filters.template_ids
                
                if filters.entity_types:
                    where_conditions.append("i.entity_type IN $entity_types")
                    params['entity_types'] = filters.entity_types
                
                if filters.statuses:
                    where_conditions.append("i.status IN $statuses")
                    params['statuses'] = filters.statuses
                
                if where_conditions:
                    query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            query_parts.append("RETURN count(i) as total")
            query = " ".join(query_parts)
            
            result = await self._storage.query(query, params)
            
            return result[0].get('total', 0) if result else 0
            
        except Exception as e:
            logger.error(f"统计实例数量失败: {e}")
            raise DataStorageError(f"统计实例数量失败: {e}")
    
    async def _validate_instance(self, instance: EntityInstance) -> None:
        """验证实例数据"""
        if not instance.id:
            raise ValidationError("实例ID不能为空")
        
        if not instance.template_id:
            raise ValidationError("模板ID不能为空")
        
        if not instance.entity_type:
            raise ValidationError("实体类型不能为空")
        
        if not instance.status:
            raise ValidationError("实例状态不能为空")
        
        # 验证状态值
        valid_statuses = ['active', 'inactive', 'deleted', 'suspended']
        if instance.status not in valid_statuses:
            raise ValidationError(f"无效的实例状态: {instance.status}")
    
    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """解析日期时间字符串"""
        if not datetime_str:
            return None
        
        try:
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None
    
    def _create_template_from_data(self, template_data: Dict[str, Any]) -> 'EntityTemplate':
        """从模板数据创建模板对象"""

        
        return EntityTemplate(
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