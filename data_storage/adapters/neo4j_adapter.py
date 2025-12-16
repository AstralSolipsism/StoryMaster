"""
Neo4j图数据库适配器实现

提供Neo4j图数据库的连接和操作功能。
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone

from neo4j import GraphDatabase, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
from ..interfaces import (
    IStorageAdapter,
    Entity,
    EntityTemplate,
    EntityInstance,
    Relationship,
    EntityType,
)


class Neo4jAdapter(IStorageAdapter):
    """Neo4j图数据库适配器"""
    
    def __init__(self, uri: str, username: str, password: str,
                 max_connection_lifetime: int = 3600, max_connection_pool_size: int = 50):
        """
        初始化Neo4j适配器
        
        Args:
            uri: Neo4j数据库URI
            username: 用户名
            password: 密码
            max_connection_lifetime: 最大连接生命周期（秒）
            max_connection_pool_size: 最大连接池大小
        """
        import hashlib
        import os
        import secrets
        
        self.uri = uri
        self.username = username
        # 使用更安全的密码哈希算法，添加盐值
        self._salt = secrets.token_hex(16)
        self._password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            self._salt.encode(),
            100000  # 迭代次数
        ).hex()
        # 在内存中保留明文密码仅用于连接，使用后应清除
        self._password = password
        self.max_connection_lifetime = max_connection_lifetime
        self.max_connection_pool_size = max_connection_pool_size
        
        self.driver = None
        self.async_driver = None
        self._connected = False
        self.logger = logging.getLogger(__name__)
    
    async def connect(self) -> bool:
        """连接Neo4j数据库"""
        try:
            # 创建同步驱动器（用于简单查询）
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self._password),
                max_connection_lifetime=self.max_connection_lifetime,
                max_connection_pool_size=self.max_connection_pool_size
            )
           
            # 创建异步驱动器（用于异步查询）
            self.async_driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.username, self._password),
                max_connection_lifetime=self.max_connection_lifetime,
                max_connection_pool_size=self.max_connection_pool_size
            )
            
            # 连接成功后，清除内存中的明文密码
            self._clear_password()
            
            # 测试连接
            await self._test_connection()
            
            self._connected = True
            self.logger.info(f"成功连接到Neo4j数据库: {self.uri}")
            return True
            
        except (ServiceUnavailable, AuthError) as e:
            self.logger.error(f"连接Neo4j数据库失败: {e}")
            self._connected = False
            return False
        except Exception as e:
            self.logger.error(f"连接Neo4j数据库时发生未知错误: {e}")
            self._connected = False
            return False
    
    async def disconnect(self) -> bool:
        """断开Neo4j数据库连接"""
        try:
            if self.driver:
                self.driver.close()
            if self.async_driver:
                await self.async_driver.close()
            
            self._connected = False
            self.logger.info("已断开Neo4j数据库连接")
            return True
            
        except Exception as e:
            self.logger.error(f"断开Neo4j连接时发生错误: {e}")
            return False
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected
    
    async def execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """执行查询"""
        if not self._connected:
            raise RuntimeError("Neo4j数据库未连接")
        
        params = params or {}
        
        try:
            # 使用异步驱动器执行查询
            async with self.async_driver.session(default_access_mode="READ") as session:
                result = await session.run(query, params)
                records = await result.data()
                return records
                
        except Exception as e:
            self.logger.error(f"执行查询时发生错误: {e}")
            self.logger.error(f"查询语句: {query}")
            self.logger.error(f"参数: {params}")
            raise
    
    async def execute_transaction(self, operations: List[Tuple[str, Dict[str, Any]]]) -> bool:
        """执行事务"""
        if not self._connected:
            raise RuntimeError("Neo4j数据库未连接")
        
        try:
            # 使用异步驱动器执行事务
            async with self.async_driver.session(default_access_mode="WRITE") as session:
                async with session.begin_transaction() as tx:
                    for query, params in operations:
                        await tx.run(query, params or {})
                    
                    # 自动提交事务
                    await tx.commit()
            
            self.logger.debug(f"成功执行事务，包含 {len(operations)} 个操作")
            return True
            
        except Exception as e:
            self.logger.error(f"执行事务时发生错误: {e}")
            return False
    
    async def create_entity(self, entity_type: EntityType, entity_data: Dict[str, Any]) -> str:
        """创建实体"""
        entity_id = entity_data.get("id")
        if not entity_id:
            raise ValueError("实体ID不能为空")
        
        # 构建创建查询
        labels = self._get_entity_labels(entity_type)
        properties = self._build_properties_string(entity_data)
        
        query = f"CREATE (e:{labels} {properties}) RETURN e.id"
        params = entity_data
        
        results = await self.execute_query(query, params)
        
        if results:
            self.logger.debug(f"成功创建实体: {entity_type.value}:{entity_id}")
            return entity_id
        else:
            raise RuntimeError(f"创建实体失败: {entity_type.value}:{entity_id}")
    
    async def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """获取实体"""
        query = "MATCH (e) WHERE e.id = $entity_id RETURN e"
        params = {"entity_id": entity_id}
        
        results = await self.execute_query(query, params)
        
        if results:
            return results[0]["e"]
        return None
    
    async def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> bool:
        """更新实体"""
        if not updates:
            return True
        
        # 添加更新时间
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # 构建更新查询
        set_clauses = [f"e.{k} = ${k}" for k in updates.keys()]
        query = f"MATCH (e) WHERE e.id = $entity_id SET {', '.join(set_clauses)} RETURN e"
        params = {"entity_id": entity_id, **updates}
        
        results = await self.execute_query(query, params)
        
        if results:
            self.logger.debug(f"成功更新实体: {entity_id}")
            return True
        else:
            self.logger.warning(f"更新实体失败，实体不存在: {entity_id}")
            return False
    
    async def delete_entity(self, entity_id: str) -> bool:
        """删除实体"""
        query = "MATCH (e) WHERE e.id = $entity_id DETACH DELETE e"
        params = {"entity_id": entity_id}
        
        try:
            await self.execute_query(query, params)
            self.logger.debug(f"成功删除实体: {entity_id}")
            return True
        except Exception as e:
            self.logger.error(f"删除实体时发生错误: {e}")
            return False
    
    async def create_relationship(self, from_entity_id: str, to_entity_id: str,
                                relationship_type: str, properties: Dict[str, Any] = None) -> str:
        """创建关系"""
        # 验证关系类型，防止注入攻击
        if not self._is_valid_relationship_type(relationship_type):
            raise ValueError(f"无效的关系类型: {relationship_type}")
            
        relationship_id = f"{from_entity_id}_{relationship_type}_{to_entity_id}"
        properties = properties or {}
        
        # 使用参数化查询，动态构建关系类型
        query = f"""
        MATCH (a), (b)
        WHERE a.id = $from_id AND b.id = $to_id
        CREATE (a)-[r:{relationship_type} {{properties}}]->(b)
        SET r.id = $relationship_id
        RETURN r.id
        """
        
        params = {
            "from_id": from_entity_id,
            "to_id": to_entity_id,
            "properties": properties,
            "relationship_id": relationship_id
        }
        
        results = await self.execute_query(query, params)
        
        if results:
            self.logger.debug(f"成功创建关系: {relationship_id}")
            return relationship_id
        else:
            raise RuntimeError(f"创建关系失败: {relationship_id}")
    
    async def get_relationships(self, entity_id: str,
                               relationship_type: Optional[str] = None,
                               direction: str = "both") -> List[Dict[str, Any]]:
        """获取实体的关系"""
        if direction == "outgoing":
            query = "MATCH (a)-[r]->(b) WHERE a.id = $entity_id"
        elif direction == "incoming":
            query = "MATCH (a)<-[r]-(b) WHERE a.id = $entity_id"
        else:  # both
            query = "MATCH (a)-[r]-(b) WHERE a.id = $entity_id"
        
        if relationship_type:
            # 验证关系类型，防止注入攻击
            if not self._is_valid_relationship_type(relationship_type):
                raise ValueError(f"无效的关系类型: {relationship_type}")
            query += f" AND type(r) = $relationship_type"
            params = {"entity_id": entity_id, "relationship_type": relationship_type}
        else:
            params = {"entity_id": entity_id}
        
        query += " RETURN a, r, b"
        
        results = await self.execute_query(query, params)
        
        relationships = []
        for result in results:
            relationships.append({
                "from": result["a"],
                "relationship": result["r"],
                "to": result["b"]
            })
        
        return relationships
    
    async def create_instance_from_template(self, template_id: str, instance_data: Dict[str, Any]) -> str:
        """基于模板创建实例"""
        # 获取模板
        template = await self.get_entity(template_id)
        if not template:
            raise ValueError(f"模板不存在: {template_id}")
        
        # 生成实例ID
        instance_id = instance_data.get("id")
        if not instance_id:
            instance_id = f"{template_id}_instance_{datetime.utcnow().timestamp()}"
        
        # 合并模板和实例数据
        merged_data = {**template, **instance_data}
        merged_data["id"] = instance_id
        merged_data["template_id"] = template_id
        merged_data["created_at"] = datetime.now(timezone.utc).isoformat()
        
        # 确定实例类型
        instance_type = self._get_instance_type_from_template(template_id)
        
        # 创建实例
        await self.create_entity(instance_type, merged_data)
        
        # 创建模板与实例的关系
        await self.create_relationship(template_id, instance_id, "HAS_INSTANCE")
        
        self.logger.debug(f"成功创建实例: {instance_id} 基于模板: {template_id}")
        return instance_id
    
    async def _test_connection(self):
        """测试连接"""
        query = "RETURN 1 as test"
        result = await self.execute_query(query)
        if not result or result[0]["test"] != 1:
            raise RuntimeError("连接测试失败")
    
    def _get_entity_labels(self, entity_type: EntityType) -> str:
        """获取实体标签"""
        return f"{entity_type.value}:Entity"
    
    def _get_instance_type_from_template(self, template_id: str) -> EntityType:
        """根据模板ID获取实例类型"""
        if "spell" in template_id.lower():
            return EntityType.SPELL_INSTANCE
        elif "item" in template_id.lower():
            return EntityType.ITEM_INSTANCE
        elif "npc" in template_id.lower():
            return EntityType.NPC_INSTANCE
        elif "scene" in template_id.lower():
            return EntityType.SCENE_INSTANCE
        else:
            return EntityType.CHARACTER  # 默认类型
    
    def _build_properties_string(self, properties: Dict[str, Any]) -> str:
        """构建属性字符串"""
        if not properties:
            return "{}"
        
        prop_list = []
        for key, value in properties.items():
            if isinstance(value, str):
                # 转义字符串中的单引号，防止注入
                escaped_value = value.replace("'", "\\'")
                prop_list.append(f"{key}: '{escaped_value}'")
            elif isinstance(value, (int, float)):
                prop_list.append(f"{key}: {value}")
            elif isinstance(value, bool):
                prop_list.append(f"{key}: {str(value).lower()}")
            elif isinstance(value, dict):
                prop_list.append(f"{key}: {self._dict_to_cypher(value)}")
            else:
                # 转义其他类型的字符串表示
                escaped_value = str(value).replace("'", "\\'")
                prop_list.append(f"{key}: '{escaped_value}'")
        
        return "{" + ", ".join(prop_list) + "}"
    
    def _dict_to_cypher(self, d: Dict[str, Any]) -> str:
        """将字典转换为Cypher格式"""
        if not d:
            return "{}"
        
        items = []
        for key, value in d.items():
            if isinstance(value, str):
                items.append(f"{key}: '{value}'")
            elif isinstance(value, (int, float)):
                items.append(f"{key}: {value}")
            elif isinstance(value, bool):
                items.append(f"{key}: {str(value).lower()}")
            elif isinstance(value, dict):
                items.append(f"{key}: {self._dict_to_cypher(value)}")
            else:
                items.append(f"{key}: '{str(value)}'")
        
        return "{" + ", ".join(items) + "}"
    
    def _is_valid_relationship_type(self, relationship_type: str) -> bool:
        """验证关系类型是否安全，防止注入攻击"""
        import re
        # 只允许字母、数字和下划线
        pattern = r'^[a-zA-Z0-9_]+$'
        return bool(re.match(pattern, relationship_type))
    
    def _clear_password(self) -> None:
        """清除内存中的明文密码"""
        if hasattr(self, '_password'):
            delattr(self, '_password')
            # 尝试覆盖内存中的密码数据
            self._password = None
            # 不强制垃圾回收，让Python的垃圾回收器自然处理
    
    def __del__(self):
        """析构函数，确保密码被清除"""
        self._clear_password()