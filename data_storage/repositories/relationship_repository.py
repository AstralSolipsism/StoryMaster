"""
关系仓库实现

提供关系的数据访问操作，包括CRUD操作和复杂查询。
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from ..interfaces import (
    IRelationshipRepository,
    IStorageAdapter,
    ICacheManager,
    Relationship,
    RelationshipFilter,
    QueryResult,
    DataStorageError,
    ValidationError
)

logger = logging.getLogger(__name__)


class RelationshipRepository(IRelationshipRepository):
    """关系仓库实现"""
    
    def __init__(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ):
        """
        初始化关系仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器
        """
        self._storage = storage_adapter
        self._cache = cache_manager
        
        logger.info("关系仓库初始化完成")
    
    async def create(self, relationship: Relationship) -> Relationship:
        """
        创建关系
        
        Args:
            relationship: 关系对象
            
        Returns:
            创建的关系
        """
        try:
            # 验证关系
            await self._validate_relationship(relationship)
            
            # 检查是否已存在
            existing = await self.get_by_id(relationship.id)
            if existing:
                raise ValidationError(f"关系已存在: {relationship.id}")
            
            # 创建关系
            query = """
            MATCH (source:Entity {id: $source_id})
            MATCH (target:Entity {id: $target_id})
            CREATE (source)-[r:RELATIONSHIP {
                id: $id,
                type: $type,
                name: $name,
                description: $description,
                properties: $properties,
                weight: $weight,
                created_at: $created_at,
                updated_at: $updated_at
            }]->(target)
            RETURN r
            """
            
            params = {
                'source_id': relationship.source_id,
                'target_id': relationship.target_id,
                'id': relationship.id,
                'type': relationship.type,
                'name': relationship.name,
                'description': relationship.description,
                'properties': relationship.properties,
                'weight': relationship.weight,
                'created_at': relationship.created_at.isoformat() if relationship.created_at else datetime.now().isoformat(),
                'updated_at': relationship.updated_at.isoformat() if relationship.updated_at else datetime.now().isoformat()
            }
            
            result = await self._storage.query(query, params)
            
            if not result:
                raise DataStorageError("创建关系失败")
            
            # 缓存关系
            if self._cache:
                await self._cache.set(
                    f"relationship:{relationship.id}",
                    relationship.dict(),
                    ttl=3600  # 1小时
                )
            
            logger.info(f"创建关系成功: {relationship.id}")
            return relationship
            
        except Exception as e:
            logger.error(f"创建关系失败: {e}")
            raise DataStorageError(f"创建关系失败: {e}")
    
    async def get_by_id(self, relationship_id: str) -> Optional[Relationship]:
        """
        根据ID获取关系
        
        Args:
            relationship_id: 关系ID
            
        Returns:
            关系对象或None
        """
        try:
            # 先从缓存获取
            if self._cache:
                cached_data = await self._cache.get(f"relationship:{relationship_id}")
                if cached_data:
                    return Relationship(**cached_data)
            
            # 从存储获取
            query = """
            MATCH (source:Entity)-[r:RELATIONSHIP {id: $relationship_id}]->(target:Entity)
            RETURN r, source.id as source_id, target.id as target_id
            """
            
            result = await self._storage.query(query, {"relationship_id": relationship_id})
            
            if not result:
                return None
            
            record = result[0]
            rel_data = record.get('r')
            
            relationship = Relationship(
                id=rel_data.get('id'),
                source_id=record.get('source_id'),
                target_id=record.get('target_id'),
                type=rel_data.get('type'),
                name=rel_data.get('name'),
                description=rel_data.get('description'),
                properties=rel_data.get('properties', {}),
                weight=rel_data.get('weight', 1.0),
                created_at=self._parse_datetime(rel_data.get('created_at')),
                updated_at=self._parse_datetime(rel_data.get('updated_at'))
            )
            
            # 缓存关系
            if self._cache:
                await self._cache.set(
                    f"relationship:{relationship_id}",
                    relationship.dict(),
                    ttl=3600
                )
            
            return relationship
            
        except Exception as e:
            logger.error(f"获取关系失败: {e}")
            raise DataStorageError(f"获取关系失败: {e}")
    
    async def update(self, relationship: Relationship) -> Relationship:
        """
        更新关系
        
        Args:
            relationship: 关系对象
            
        Returns:
            更新后的关系
        """
        try:
            # 验证关系
            await self._validate_relationship(relationship)
            
            # 检查是否存在
            existing = await self.get_by_id(relationship.id)
            if not existing:
                raise ValidationError(f"关系不存在: {relationship.id}")
            
            # 更新关系
            query = """
            MATCH (source:Entity)-[r:RELATIONSHIP {id: $id}]->(target:Entity)
            SET r.type = $type,
                r.name = $name,
                r.description = $description,
                r.properties = $properties,
                r.weight = $weight,
                r.updated_at = $updated_at
            RETURN r
            """
            
            params = {
                'id': relationship.id,
                'type': relationship.type,
                'name': relationship.name,
                'description': relationship.description,
                'properties': relationship.properties,
                'weight': relationship.weight,
                'updated_at': datetime.now().isoformat()
            }
            
            result = await self._storage.query(query, params)
            
            if not result:
                raise DataStorageError("更新关系失败")
            
            # 更新缓存
            if self._cache:
                await self._cache.set(
                    f"relationship:{relationship.id}",
                    relationship.dict(),
                    ttl=3600
                )
            
            logger.info(f"更新关系成功: {relationship.id}")
            return relationship
            
        except Exception as e:
            logger.error(f"更新关系失败: {e}")
            raise DataStorageError(f"更新关系失败: {e}")
    
    async def delete(self, relationship_id: str) -> bool:
        """
        删除关系
        
        Args:
            relationship_id: 关系ID
            
        Returns:
            是否删除成功
        """
        try:
            # 删除关系
            query = """
            MATCH ()-[r:RELATIONSHIP {id: $relationship_id}]->()
            DELETE r
            """
            
            await self._storage.execute(query, {"relationship_id": relationship_id})
            
            # 从缓存删除
            if self._cache:
                await self._cache.delete(f"relationship:{relationship_id}")
            
            logger.info(f"删除关系成功: {relationship_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除关系失败: {e}")
            return False
    
    async def find(self, filters: RelationshipFilter) -> QueryResult:
        """
        查找关系
        
        Args:
            filters: 过滤条件
            
        Returns:
            查询结果
        """
        try:
            # 构建查询
            query_parts = ["MATCH (source:Entity)-[r:RELATIONSHIP]->(target:Entity)"]
            where_conditions = []
            params = {}
            
            # 添加过滤条件
            if filters.relationship_types:
                where_conditions.append("r.type IN $relationship_types")
                params['relationship_types'] = filters.relationship_types
            
            if filters.source_ids:
                where_conditions.append("source.id IN $source_ids")
                params['source_ids'] = filters.source_ids
            
            if filters.target_ids:
                where_conditions.append("target.id IN $target_ids")
                params['target_ids'] = filters.target_ids
            
            if filters.name_pattern:
                where_conditions.append("r.name CONTAINS $name_pattern")
                params['name_pattern'] = filters.name_pattern
            
            if filters.property_filters:
                for prop_name, prop_value in filters.property_filters.items():
                    where_conditions.append(f"r.properties.{prop_name} = $prop_{prop_name}")
                    params[f'prop_{prop_name}'] = prop_value
            
            if filters.min_weight is not None:
                where_conditions.append("r.weight >= $min_weight")
                params['min_weight'] = filters.min_weight
            
            if filters.max_weight is not None:
                where_conditions.append("r.weight <= $max_weight")
                params['max_weight'] = filters.max_weight
            
            if filters.created_after:
                where_conditions.append("r.created_at >= $created_after")
                params['created_after'] = filters.created_after.isoformat()
            
            if filters.created_before:
                where_conditions.append("r.created_at <= $created_before")
                params['created_before'] = filters.created_before.isoformat()
            
            # 添加WHERE子句
            if where_conditions:
                query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            # 添加排序
            if filters.order_by:
                order_direction = "DESC" if filters.order_desc else "ASC"
                query_parts.append(f"ORDER BY r.{filters.order_by} {order_direction}")
            
            # 添加分页
            if filters.limit:
                query_parts.append(f"LIMIT {filters.limit}")
            
            if filters.offset:
                query_parts.append(f"SKIP {filters.offset}")
            
            query = " ".join(query_parts) + " RETURN r, source.id as source_id, target.id as target_id"
            
            # 执行查询
            result = await self._storage.query(query, params)
            
            # 转换结果
            relationships = []
            for record in result:
                rel_data = record.get('r')
                if rel_data:
                    relationship = Relationship(
                        id=rel_data.get('id'),
                        source_id=record.get('source_id'),
                        target_id=record.get('target_id'),
                        type=rel_data.get('type'),
                        name=rel_data.get('name'),
                        description=rel_data.get('description'),
                        properties=rel_data.get('properties', {}),
                        weight=rel_data.get('weight', 1.0),
                        created_at=self._parse_datetime(rel_data.get('created_at')),
                        updated_at=self._parse_datetime(rel_data.get('updated_at'))
                    )
                    relationships.append(relationship)
            
            # 获取总数
            count_query = "MATCH (source:Entity)-[r:RELATIONSHIP]->(target:Entity"
            if where_conditions:
                count_query += " WHERE " + " AND ".join(where_conditions)
            count_query += ") RETURN count(r) as total"
            
            count_result = await self._storage.query(count_query, params)
            total_count = count_result[0].get('total', 0) if count_result else 0
            
            return QueryResult(
                items=relationships,
                total_count=total_count,
                has_more=(filters.offset or 0) + len(relationships) < total_count
            )
            
        except Exception as e:
            logger.error(f"查找关系失败: {e}")
            raise DataStorageError(f"查找关系失败: {e}")
    
    async def find_by_source(self, source_id: str) -> List[Relationship]:
        """
        根据源实体查找关系
        
        Args:
            source_id: 源实体ID
            
        Returns:
            关系列表
        """
        try:
            query = """
            MATCH (source:Entity {id: $source_id})-[r:RELATIONSHIP]->(target:Entity)
            RETURN r, source.id as source_id, target.id as target_id
            """
            
            result = await self._storage.query(query, {"source_id": source_id})
            
            relationships = []
            for record in result:
                rel_data = record.get('r')
                if rel_data:
                    relationship = Relationship(
                        id=rel_data.get('id'),
                        source_id=record.get('source_id'),
                        target_id=record.get('target_id'),
                        type=rel_data.get('type'),
                        name=rel_data.get('name'),
                        description=rel_data.get('description'),
                        properties=rel_data.get('properties', {}),
                        weight=rel_data.get('weight', 1.0),
                        created_at=self._parse_datetime(rel_data.get('created_at')),
                        updated_at=self._parse_datetime(rel_data.get('updated_at'))
                    )
                    relationships.append(relationship)
            
            return relationships
            
        except Exception as e:
            logger.error(f"根据源实体查找关系失败: {e}")
            raise DataStorageError(f"根据源实体查找关系失败: {e}")
    
    async def find_by_target(self, target_id: str) -> List[Relationship]:
        """
        根据目标实体查找关系
        
        Args:
            target_id: 目标实体ID
            
        Returns:
            关系列表
        """
        try:
            query = """
            MATCH (source:Entity)-[r:RELATIONSHIP]->(target:Entity {id: $target_id})
            RETURN r, source.id as source_id, target.id as target_id
            """
            
            result = await self._storage.query(query, {"target_id": target_id})
            
            relationships = []
            for record in result:
                rel_data = record.get('r')
                if rel_data:
                    relationship = Relationship(
                        id=rel_data.get('id'),
                        source_id=record.get('source_id'),
                        target_id=record.get('target_id'),
                        type=rel_data.get('type'),
                        name=rel_data.get('name'),
                        description=rel_data.get('description'),
                        properties=rel_data.get('properties', {}),
                        weight=rel_data.get('weight', 1.0),
                        created_at=self._parse_datetime(rel_data.get('created_at')),
                        updated_at=self._parse_datetime(rel_data.get('updated_at'))
                    )
                    relationships.append(relationship)
            
            return relationships
            
        except Exception as e:
            logger.error(f"根据目标实体查找关系失败: {e}")
            raise DataStorageError(f"根据目标实体查找关系失败: {e}")
    
    async def find_by_type(self, relationship_type: str) -> List[Relationship]:
        """
        根据类型查找关系
        
        Args:
            relationship_type: 关系类型
            
        Returns:
            关系列表
        """
        try:
            query = """
            MATCH (source:Entity)-[r:RELATIONSHIP {type: $relationship_type}]->(target:Entity)
            RETURN r, source.id as source_id, target.id as target_id
            """
            
            result = await self._storage.query(query, {"relationship_type": relationship_type})
            
            relationships = []
            for record in result:
                rel_data = record.get('r')
                if rel_data:
                    relationship = Relationship(
                        id=rel_data.get('id'),
                        source_id=record.get('source_id'),
                        target_id=record.get('target_id'),
                        type=rel_data.get('type'),
                        name=rel_data.get('name'),
                        description=rel_data.get('description'),
                        properties=rel_data.get('properties', {}),
                        weight=rel_data.get('weight', 1.0),
                        created_at=self._parse_datetime(rel_data.get('created_at')),
                        updated_at=self._parse_datetime(rel_data.get('updated_at'))
                    )
                    relationships.append(relationship)
            
            return relationships
            
        except Exception as e:
            logger.error(f"根据类型查找关系失败: {e}")
            raise DataStorageError(f"根据类型查找关系失败: {e}")
    
    async def find_between_entities(
        self,
        source_id: str,
        target_id: str,
        relationship_type: Optional[str] = None
    ) -> List[Relationship]:
        """
        查找两个实体之间的关系
        
        Args:
            source_id: 源实体ID
            target_id: 目标实体ID
            relationship_type: 关系类型（可选）
            
        Returns:
            关系列表
        """
        try:
            query_parts = [
                "MATCH (source:Entity {id: $source_id})-[r:RELATIONSHIP]->(target:Entity {id: $target_id})"
            ]
            
            params = {
                'source_id': source_id,
                'target_id': target_id
            }
            
            if relationship_type:
                query_parts.append("WHERE r.type = $relationship_type")
                params['relationship_type'] = relationship_type
            
            query_parts.append("RETURN r, source.id as source_id, target.id as target_id")
            query = " ".join(query_parts)
            
            result = await self._storage.query(query, params)
            
            relationships = []
            for record in result:
                rel_data = record.get('r')
                if rel_data:
                    relationship = Relationship(
                        id=rel_data.get('id'),
                        source_id=record.get('source_id'),
                        target_id=record.get('target_id'),
                        type=rel_data.get('type'),
                        name=rel_data.get('name'),
                        description=rel_data.get('description'),
                        properties=rel_data.get('properties', {}),
                        weight=rel_data.get('weight', 1.0),
                        created_at=self._parse_datetime(rel_data.get('created_at')),
                        updated_at=self._parse_datetime(rel_data.get('updated_at'))
                    )
                    relationships.append(relationship)
            
            return relationships
            
        except Exception as e:
            logger.error(f"查找实体间关系失败: {e}")
            raise DataStorageError(f"查找实体间关系失败: {e}")
    
    async def count(self, filters: Optional[RelationshipFilter] = None) -> int:
        """
        统计关系数量
        
        Args:
            filters: 过滤条件（可选）
            
        Returns:
            关系数量
        """
        try:
            query_parts = ["MATCH (source:Entity)-[r:RELATIONSHIP]->(target:Entity)"]
            params = {}
            
            if filters:
                where_conditions = []
                
                if filters.relationship_types:
                    where_conditions.append("r.type IN $relationship_types")
                    params['relationship_types'] = filters.relationship_types
                
                if filters.source_ids:
                    where_conditions.append("source.id IN $source_ids")
                    params['source_ids'] = filters.source_ids
                
                if filters.target_ids:
                    where_conditions.append("target.id IN $target_ids")
                    params['target_ids'] = filters.target_ids
                
                if filters.name_pattern:
                    where_conditions.append("r.name CONTAINS $name_pattern")
                    params['name_pattern'] = filters.name_pattern
                
                if where_conditions:
                    query_parts.append("WHERE " + " AND ".join(where_conditions))
            
            query_parts.append("RETURN count(r) as total")
            query = " ".join(query_parts)
            
            result = await self._storage.query(query, params)
            
            return result[0].get('total', 0) if result else 0
            
        except Exception as e:
            logger.error(f"统计关系数量失败: {e}")
            raise DataStorageError(f"统计关系数量失败: {e}")
    
    async def _validate_relationship(self, relationship: Relationship) -> None:
        """验证关系数据"""
        if not relationship.id:
            raise ValidationError("关系ID不能为空")
        
        if not relationship.source_id:
            raise ValidationError("源实体ID不能为空")
        
        if not relationship.target_id:
            raise ValidationError("目标实体ID不能为空")
        
        if not relationship.type:
            raise ValidationError("关系类型不能为空")
        
        if relationship.source_id == relationship.target_id:
            raise ValidationError("源实体和目标实体不能相同")
    
    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """解析日期时间字符串"""
        if not datetime_str:
            return None
        
        try:
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None