"""
实体仓库实现

提供实体的数据访问操作，包括CRUD操作和复杂查询。
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from ..interfaces import (
    IEntityRepository,
    IStorageAdapter,
    ICacheManager,
    Entity,
    EntityFilter,
    QueryResult,
    DataStorageError,
    ValidationError
)

logger = logging.getLogger(__name__)


class EntityRepository(IEntityRepository):
    """实体仓库实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ):
        """
        初始化实体仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器
        """
        self._storage = storage_adapter
        self._cache = cache_manager
        
        logger.info("实体仓库初始化完成")
    
    async def create(self, entity: Entity) -> Entity:
        """
        创建实体
        
        Args:
            entity: 实体对象
            
        Returns:
            创建的实体
        """
        try:
            # 验证实体
            await self._validate_entity(entity)
            
            # 检查是否已存在
            existing = await self.get_by_id(entity.id)
            if existing:
                raise ValidationError(f"实体已存在: {entity.id}")
            
            # 创建实体节点
            query = """
            CREATE (e:Entity {
                id: $id,
                entity_type: $entity_type,
                properties: $properties,
                created_at: $created_at,
                updated_at: $updated_at
            })
            RETURN e
            """
            
            params = {
                'id': entity.id,
                'entity_type': entity.entity_type,
                'properties': entity.properties,
                'created_at': entity.created_at.isoformat() if entity.created_at else datetime.now().isoformat(),
                'updated_at': entity.updated_at.isoformat() if entity.updated_at else datetime.now().isoformat()
            }
            
            result = await self._storage.query(query, params)
            
            if not result:
                raise DataStorageError("创建实体失败")
            
            # 缓存实体
            if self._cache:
                await self._cache.set(
                    f"entity:{entity.id}",
                    entity.dict(),
                    ttl=3600  # 1小时
                )
            
            logger.info(f"创建实体成功: {entity.id}")
            return entity
            
        except Exception as e:
            logger.error(f"创建实体失败: {e}")
            raise DataStorageError(f"创建实体失败: {e}")
    
    async def get_by_id(self, entity_id: str) -> Optional[Entity]:
        """
        根据ID获取实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            实体对象或None
        """
        try:
            # 先从缓存获取
            if self._cache:
                cached_data = await self._cache.get(f"entity:{entity_id}")
                if cached_data:
                    return Entity(**cached_data)
            
            # 从存储获取
            query = """
            MATCH (e:Entity {id: $entity_id})
            RETURN e
            """
            
            result = await self._storage.query(query, {"entity_id": entity_id})
            
            if not result:
                return None
            
            entity_data = result[0].get('e')
            entity = entity = self._create_entity_from_data(entity_data)
            
            # 缓存实体
            if self._cache:
                await self._cache.set(
                    f"entity:{entity_id}",
                    entity.dict(),
                    ttl=3600
                )
            
            return entity
            
        except Exception as e:
            logger.error(f"获取实体失败: {e}")
            raise DataStorageError(f"获取实体失败: {e}")
    
    async def update(self, entity: Entity) -> Entity:
        """
        更新实体
        
        Args:
            entity: 实体对象
            
        Returns:
            更新后的实体
        """
        try:
            # 验证实体
            await self._validate_entity(entity)
            
            # 检查是否存在
            existing = await self.get_by_id(entity.id)
            if not existing:
                raise ValidationError(f"实体不存在: {entity.id}")
            
            # 更新实体
            query = """
            MATCH (e:Entity {id: $id})
            SET e.entity_type = $entity_type,
                e.properties = $properties,
                e.updated_at = $updated_at
            RETURN e
            """
            
            params = {
                'id': entity.id,
                'entity_type': entity.entity_type,
                'properties': entity.properties,
                'updated_at': datetime.now().isoformat()
            }
            
            result = await self._storage.query(query, params)
            
            if not result:
                raise DataStorageError("更新实体失败")
            
            # 更新缓存
            if self._cache:
                await self._cache.set(
                    f"entity:{entity.id}",
                    entity.dict(),
                    ttl=3600
                )
            
            logger.info(f"更新实体成功: {entity.id}")
            return entity
            
        except Exception as e:
            logger.error(f"更新实体失败: {e}")
            raise DataStorageError(f"更新实体失败: {e}")
    
    async def delete(self, entity_id: str) -> bool:
        """
        删除实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            是否删除成功
        """
        try:
            # 删除实体及其关系
            query = """
            MATCH (e:Entity {id: $entity_id})
            DETACH DELETE e
            """
            
            await self._storage.execute(query, {"entity_id": entity_id})
            
            # 从缓存删除
            if self._cache:
                await self._cache.delete(f"entity:{entity_id}")
            
            logger.info(f"删除实体成功: {entity_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除实体失败: {e}")
            return False
    
    async def find(self, filters: EntityFilter) -> QueryResult:
        """
        查找实体
        
        Args:
            filters: 过滤条件
            
        Returns:
            查询结果
        """
        try:
            # 构建查询
            query_parts = ["MATCH (e:Entity)"]
            where_conditions = []
            params = {}
            
            # 添加过滤条件
            if filters.entity_types:
                where_conditions.append("e.entity_type IN $entity_types")
                params['entity_types'] = filters.entity_types
            
            if filters.name_pattern:
                where_conditions.append("e.properties.name CONTAINS $name_pattern")
                params['name_pattern'] = filters.name_pattern
            
            if filters.property_filters:
                # 验证属性名，防止注入攻击
                allowed_props = ['name', 'description', 'entity_type']  # 预定义允许的属性
                for prop_name, prop_value in filters.property_filters.items():
                    if prop_name not in allowed_props:
                        raise ValueError(f"不允许的属性过滤: {prop_name}")
                        
                    where_conditions.append(f"e.{prop_name} = $prop_{prop_name}")
                    params[f'prop_{prop_name}'] = prop_value
            
            if filters.created_after:
                where_conditions.append("e.created_at >= $created_after")
                params['created_after'] = filters.created_after.isoformat()
            
            if filters.created_before:
                where_conditions.append("e.created_at <= $created_before")
                params['created_before'] = filters.created_before.isoformat()
            
            # 添加WHERE子句
            if where_conditions:
                query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            # 添加排序 - 使用白名单验证排序字段
            if filters.order_by:
                # 验证排序字段是否在白名单中
                allowed_fields = ['id', 'entity_type', 'created_at', 'updated_at']
                if filters.order_by not in allowed_fields:
                    raise ValueError(f"不允许的排序字段: {filters.order_by}")
                
                order_direction = "DESC" if filters.order_desc else "ASC"
                query_parts.append(f"ORDER BY e.{filters.order_by} {order_direction}")
            
            # 添加分页 - 使用参数化查询防止SQL注入
            if filters.limit:
                query_parts.append("LIMIT $limit")
                params['limit'] = filters.limit
            
            if filters.offset:
                query_parts.append("SKIP $offset")
                params['offset'] = filters.offset
            
            query = " ".join(query_parts) + " RETURN e"
            
            # 执行查询
            result = await self._storage.query(query, params)
            
            # 转换结果
            entities = []
            for record in result:
                entity_data = record.get('e')
                if entity_data:
                    entity = self._create_entity_from_data(entity_data)
                    entities.append(entity)
            
            # 获取总数
            count_query = "MATCH (e:Entity"
            if where_conditions:
                count_query += " WHERE " + " AND ".join(where_conditions)
            count_query += ") RETURN count(e) as total"
            
            count_result = await self._storage.query(count_query, params)
            total_count = count_result[0].get('total', 0) if count_result else 0
            
            return QueryResult(
                items=entities,
                total_count=total_count,
                has_more=(filters.offset or 0) + len(entities) < total_count
            )
            
        except Exception as e:
            logger.error(f"查找实体失败: {e}")
            raise DataStorageError(f"查找实体失败: {e}")
    
    async def find_by_type(self, entity_type: str) -> List[Entity]:
        """
        根据类型查找实体
        
        Args:
            entity_type: 实体类型
            
        Returns:
            实体列表
        """
        try:
            query = """
            MATCH (e:Entity {entity_type: $entity_type})
            RETURN e
            """
            
            result = await self._storage.query(query, {"entity_type": entity_type})
            
            entities = []
            for record in result:
                entity_data = record.get('e')
                if entity_data:
                    entity = self._create_entity_from_data(entity_data)
                    entities.append(entity)
            
            return entities
            
        except Exception as e:
            logger.error(f"根据类型查找实体失败: {e}")
            raise DataStorageError(f"根据类型查找实体失败: {e}")
    
    async def find_by_name(self, name: str) -> List[Entity]:
        """
        根据名称查找实体
        
        Args:
            name: 实体名称
            
        Returns:
            实体列表
        """
        try:
            query = """
            MATCH (e:Entity)
            WHERE e.properties.name = $name
            RETURN e
            """
            
            result = await self._storage.query(query, {"name": name})
            
            entities = []
            for record in result:
                entity_data = record.get('e')
                if entity_data:
                    entity = self._create_entity_from_data(entity_data)
                    entities.append(entity)
            
            return entities
            
        except Exception as e:
            logger.error(f"根据名称查找实体失败: {e}")
            raise DataStorageError(f"根据名称查找实体失败: {e}")
    
    async def search(self, search_term: str, limit: int = 10) -> List[Entity]:
        """
        搜索实体
        
        Args:
            search_term: 搜索词
            limit: 结果限制
            
        Returns:
            匹配的实体列表
        """
        try:
            query = """
            MATCH (e:Entity)
            WHERE e.properties.name CONTAINS $search_term
               OR e.properties.description CONTAINS $search_term
            RETURN e
            LIMIT $limit
            """
            
            params = {
                'search_term': search_term,
                'limit': limit
            }
            
            result = await self._storage.query(query, params)
            
            entities = []
            for record in result:
                entity_data = record.get('e')
                if entity_data:
                    entity = self._create_entity_from_data(entity_data)
                    entities.append(entity)
            
            return entities
            
        except Exception as e:
            logger.error(f"搜索实体失败: {e}")
            raise DataStorageError(f"搜索实体失败: {e}")
    
    async def count(self, filters: Optional[EntityFilter] = None) -> int:
        """
        统计实体数量
        
        Args:
            filters: 过滤条件（可选）
            
        Returns:
            实体数量
        """
        try:
            query_parts = ["MATCH (e:Entity)"]
            params = {}
            
            if filters:
                where_conditions = []
                
                if filters.entity_types:
                    where_conditions.append("e.entity_type IN $entity_types")
                    params['entity_types'] = filters.entity_types
                
                if filters.name_pattern:
                    where_conditions.append("e.properties.name CONTAINS $name_pattern")
                    params['name_pattern'] = filters.name_pattern
                
                if filters.property_filters:
                    for prop_name, prop_value in filters.property_filters.items():
                        where_conditions.append(f"e.properties.{prop_name} = $prop_{prop_name}")
                        params[f'prop_{prop_name}'] = prop_value
                
                if where_conditions:
                    query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            query_parts.append("RETURN count(e) as total")
            query = " ".join(query_parts)
            
            result = await self._storage.query(query, params)
            
            return result[0].get('total', 0) if result else 0
            
        except Exception as e:
            logger.error(f"统计实体数量失败: {e}")
            raise DataStorageError(f"统计实体数量失败: {e}")
    
    async def _validate_entity(self, entity: Entity) -> None:
        """验证实体数据"""
        if not entity.id:
            raise ValidationError("实体ID不能为空")
        
        if not entity.entity_type:
            raise ValidationError("实体类型不能为空")
        
        if not entity.properties.get('name'):
            raise ValidationError("实体名称不能为空")
    
    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """解析日期时间字符串"""
        if not datetime_str:
            return None
        
        try:
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None
        
    def _create_entity_from_data(self, entity_data: Dict[str, Any]) -> Entity:
        """从数据字典创建实体对象"""
        return Entity(
            id=entity_data.get('id'),
            entity_type=entity_data.get('entity_type'),
            properties=entity_data.get('properties', {}),
            created_at=self._parse_datetime(entity_data.get('created_at')),
            updated_at=self._parse_datetime(entity_data.get('updated_at'))
        )