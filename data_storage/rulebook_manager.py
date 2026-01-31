"""
规则书管理系统

负责游戏规则书的上传、存储、验证和管理。
支持自定义规则书，解决硬编码数据结构的问题。
"""

import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from abc import ABC, abstractmethod

from ..core.schema_manager import SchemaManager, RulebookSchema
from ..data_storage.interfaces import ValidationError, DataStorageError

logger = logging.getLogger(__name__)


# ==================== 规则书存储接口 ====================

class IRulebookStorage(ABC):
    """规则书存储接口"""
    
    @abstractmethod
    async def save_schema(self, schema: RulebookSchema) -> str:
        """保存规则书Schema"""
        pass
    
    @abstractmethod
    async def load_schema(self, schema_id: str) -> Optional[RulebookSchema]:
        """加载规则书Schema"""
        pass
    
    @abstractmethod
    async def delete_schema(self, schema_id: str) -> bool:
        """删除规则书Schema"""
        pass
    
    @abstractmethod
    async def list_schemas(self) -> List[Dict[str, Any]]:
        """列出所有规则书"""
        pass
    
    @abstractmethod
    async def schema_exists(self, schema_id: str) -> bool:
        """检查规则书是否存在"""
        pass


class FilesystemRulebookStorage(IRulebookStorage):
    """文件系统规则书存储"""
    
    def __init__(self, storage_path: str = "./data/rulebooks"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
    
    async def save_schema(self, schema: RulebookSchema) -> str:
        """保存规则书Schema到文件系统"""
        try:
            # 生成文件路径
            file_name = f"{schema.schema_id}.json"
            file_path = self.storage_path / file_name
            
            # 序列化Schema
            schema_data = self._serialize_schema(schema)
            
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(schema_data, f, indent=2, ensure_ascii=False)
            
            # 生成哈希
            schema_hash = self._generate_schema_hash(schema_data)
            
            self.logger.info(f"规则书Schema已保存: {file_path}")
            return schema_hash
            
        except Exception as e:
            raise DataStorageError(f"保存规则书Schema失败: {e}")
    
    async def load_schema(self, schema_id: str) -> Optional[RulebookSchema]:
        """从文件系统加载规则书Schema"""
        try:
            file_path = self.storage_path / f"{schema_id}.json"
            
            if not file_path.exists():
                return None
            
            # 读取并解析JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)
            
            # 反序列化为RulebookSchema对象
            return self._deserialize_schema(schema_id, schema_data)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"加载规则书Schema失败: {schema_id}, JSON解析错误: {e}")
            return None
        except Exception as e:
            self.logger.error(f"加载规则书Schema失败: {schema_id}, 错误: {e}")
            return None
    
    async def delete_schema(self, schema_id: str) -> bool:
        """删除规则书Schema"""
        try:
            file_path = self.storage_path / f"{schema_id}.json"
            
            if file_path.exists():
                file_path.unlink()
                self.logger.info(f"规则书Schema已删除: {schema_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"删除规则书Schema失败: {e}")
            return False
    
    async def list_schemas(self) -> List[Dict[str, Any]]:
        """列出所有规则书"""
        try:
            schemas = []
            
            for schema_file in self.storage_path.glob("*.json"):
                try:
                    schema_id = schema_file.stem
                    schema_data = await self._load_schema_metadata(schema_id)
                    
                    if schema_data:
                        schemas.append({
                            'schema_id': schema_id,
                            **schema_data
                        })
                except Exception as e:
                    self.logger.warning(f"无法读取Schema文件 {schema_file}: {e}")
            
            return schemas
            
        except Exception as e:
            self.logger.error(f"列出规则书失败: {e}")
            return []
    
    async def schema_exists(self, schema_id: str) -> bool:
        """检查规则书是否存在"""
        return (self.storage_path / f"{schema_id}.json").exists()
    
    async def _load_schema_metadata(self, schema_id: str) -> Optional[Dict[str, Any]]:
        """加载Schema元数据（不包含完整的Schema定义）"""
        try:
            file_path = self.storage_path / f"{schema_id}.json"
            
            with open(file_path, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)
            
            return {
                'name': schema_data.get('name', schema_id),
                'version': schema_data.get('version', '1.0.0'),
                'author': schema_data.get('author', ''),
                'description': schema_data.get('description', ''),
                'game_system': schema_data.get('game_system', ''),
                'created_at': schema_data.get('created_at'),
                'entity_count': len(schema_data.get('entities', {})),
                'is_active': schema_data.get('is_active', False)
            }
            
        except Exception as e:
            self.logger.error(f"加载Schema元数据失败: {e}")
            return None
    
    def _serialize_schema(self, schema: RulebookSchema) -> Dict[str, Any]:
        """序列化Schema为字典"""
        return {
            'schema_id': schema.schema_id,
            'name': schema.name,
            'version': schema.version,
            'author': schema.author,
            'description': schema.description,
            'game_system': schema.game_system,
            'entities': self._serialize_entities(schema.entities),
            'rules': self._serialize_rules(schema.rules),
            'created_at': schema.created_at.isoformat() if schema.created_at else None,
            'updated_at': schema.updated_at.isoformat() if schema.updated_at else None,
            'is_active': schema.is_active
        }
    
    def _deserialize_schema(self, schema_id: str, schema_data: Dict[str, Any]) -> RulebookSchema:
        """从字典反序列化Schema"""
        return RulebookSchema(
            schema_id=schema_id,
            name=schema_data.get('name', schema_id),
            version=schema_data.get('version', '1.0.0'),
            author=schema_data.get('author', ''),
            description=schema_data.get('description', ''),
            game_system=schema_data.get('game_system', ''),
            entities=self._deserialize_entities(schema_data.get('entities', {})),
            rules=self._deserialize_rules(schema_data.get('rules', {})),
            created_at=datetime.fromisoformat(schema_data['created_at']) if 'created_at' in schema_data else None,
            updated_at=datetime.fromisoformat(schema_data['updated_at']) if 'updated_at' in schema_data else None,
            is_active=schema_data.get('is_active', False)
        )
    
    def _serialize_entities(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """序列化实体定义"""
        serialized = {}
        
        for entity_id, entity_def in entities.items():
            serialized[entity_id] = {
                'entity_type': entity_id,
                'label': entity_def.label,
                'plural_label': entity_def.plural_label,
                'properties': self._serialize_properties(entity_def.properties),
                'relationships': self._serialize_relationships(entity_def.relationships),
                'validation_rules': entity_def.validation_rules
            }
        
        return serialized
    
    def _deserialize_entities(self, entities_data: Dict[str, Any]) -> Dict[str, Any]:
        """反序列化实体定义"""
        entities = {}
        
        for entity_id, entity_data in entities_data.items():
            entities[entity_id] = SchemaManager.EntityDefinition(
                entity_type=entity_id,
                label=entity_data.get('label', entity_id),
                plural_label=entity_data.get('plural_label', f"{entity_id}s"),
                properties=self._deserialize_properties(entity_data.get('properties', {})),
                relationships=self._deserialize_relationships(entity_data.get('relationships', {})),
                validation_rules=entity_data.get('validation_rules', {})
            )
        
        return entities
    
    def _serialize_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """序列化属性定义"""
        serialized = {}
        
        for prop_id, prop_def in properties.items():
            serialized[prop_id] = {
                'name': prop_def.name,
                'type': prop_def.type,
                'required': prop_def.required,
                'description': prop_def.description,
                'default': prop_def.default,
                'min_value': prop_def.min_value,
                'max_value': prop_def.max_value,
                'enum_values': prop_def.enum_values,
                'validation_regex': prop_def.validation_regex
            }
        
        return serialized
    
    def _deserialize_properties(self, props_data: Dict[str, Any]) -> Dict[str, Any]:
        """反序列化属性定义"""
        properties = {}
        
        for prop_id, prop_data in props_data.items():
            properties[prop_id] = SchemaManager.PropertyDefinition(
                name=prop_data.get('name', prop_id),
                type=prop_data.get('type', 'string'),
                required=prop_data.get('required', True),
                description=prop_data.get('description', ''),
                default=prop_data.get('default'),
                min_value=prop_data.get('min_value'),
                max_value=prop_data.get('max_value'),
                enum_values=prop_data.get('enum_values'),
                validation_regex=prop_data.get('validation_regex')
            )
        
        return properties
    
    def _serialize_relationships(self, relationships: Dict[str, Any]) -> Dict[str, Any]:
        """序列化关系定义"""
        serialized = {}
        
        for rel_id, rel_def in relationships.items():
            serialized[rel_id] = {
                'name': rel_def.name,
                'target_entity_type': rel_def.target_entity_type,
                'relationship_type': rel_def.relationship_type,
                'inverse_relationship': rel_def.inverse_relationship,
                'properties': rel_def.properties
            }
        
        return serialized
    
    def _deserialize_relationships(self, rels_data: Dict[str, Any]) -> Dict[str, Any]:
        """反序列化关系定义"""
        relationships = {}
        
        for rel_id, rel_data in rels_data.items():
            relationships[rel_id] = SchemaManager.RelationshipDefinition(
                name=rel_id,
                target_entity_type=rel_data.get('target_entity_type', ''),
                relationship_type=rel_data.get('relationship_type', 'one_to_many'),
                inverse_relationship=rel_data.get('inverse_relationship'),
                properties=rel_data.get('properties', {})
            )
        
        return relationships
    
    def _serialize_rules(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """序列化规则定义"""
        serialized = {}
        
        for rule_id, rule_def in rules.items():
            serialized[rule_id] = {
                'type': rule_def.type,
                'description': rule_def.description,
                'expression': rule_def.expression,
                'parameters': rule_def.parameters,
                'applicable_to': rule_def.applicable_to
            }
        
        return serialized
    
    def _deserialize_rules(self, rules_data: Dict[str, Any]) -> Dict[str, Any]:
        """反序列化规则定义"""
        rules = {}
        
        for rule_id, rule_data in rules_data.items():
            rules[rule_id] = SchemaManager.RuleDefinition(
                name=rule_id,
                type=rule_data.get('type', 'validation'),
                description=rule_data.get('description', ''),
                expression=rule_data.get('expression', ''),
                parameters=rule_data.get('parameters', {}),
                applicable_to=rule_data.get('applicable_to', [])
            )
        
        return rules
    
    def _generate_schema_hash(self, schema_data: Dict[str, Any]) -> str:
        """生成Schema的哈希值"""
        # 排除时间字段，使哈希稳定
        stable_data = {k: v for k, v in schema_data.items() 
                      if k not in ['created_at', 'updated_at']}
        
        # 生成哈希
        json_str = json.dumps(stable_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()


class DatabaseRulebookStorage(IRulebookStorage):
    """数据库规则书存储（Neo4j）"""
    
    def __init__(self, neo4j_driver):
        self.neo4j = neo4j_driver
        self.logger = logging.getLogger(__name__)
    
    async def save_schema(self, schema: RulebookSchema) -> str:
        """保存规则书Schema到数据库"""
        try:
            # 序列化Schema
            schema_data = self._serialize_schema(schema)
            
            # 创建规则书记录
            query = """
            CREATE (rs:RulebookSchema {
                id: $schema_id,
                name: $name,
                version: $version,
                author: $author,
                description: $description,
                game_system: $game_system,
                schema_data: $schema_data,
                created_at: $created_at,
                updated_at: $updated_at,
                is_active: $is_active
            })
            RETURN rs.id
            """
            
            params = {
                'schema_id': schema.schema_id,
                'name': schema.name,
                'version': schema.version,
                'author': schema.author,
                'description': schema.description,
                'game_system': schema.game_system,
                'schema_data': json.dumps(schema_data),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'is_active': False
            }
            
            async with self.neo4j.session() as session:
                result = await session.run(query, params)
                records = await result.data()
            
                if not records:
                    raise DataStorageError("创建规则书记录失败")
                
                schema_hash = self._generate_schema_hash(schema_data)
                self.logger.info(f"规则书Schema已保存到数据库: {schema.schema_id}")
                
                return schema_hash
            
        except Exception as e:
            raise DataStorageError(f"保存规则书Schema到数据库失败: {e}")
    
    async def load_schema(self, schema_id: str) -> Optional[RulebookSchema]:
        """从数据库加载规则书Schema"""
        try:
            query = """
            MATCH (rs:RulebookSchema)
            WHERE rs.id = $schema_id
            RETURN rs
            """
            
            async with self.neo4j.session() as session:
                result = await session.run(query, {"schema_id": schema_id})
                records = await result.data()
                
                if not records:
                    return None
                
                schema_data = records[0]['rs']
                
                # 反序列化Schema
                return self._deserialize_schema(schema_id, json.loads(schema_data['schema_data']))
            
        except Exception as e:
            self.logger.error(f"从数据库加载Schema失败: {schema_id}, 错误: {e}")
            return None
    
    async def delete_schema(self, schema_id: str) -> bool:
        """从数据库删除规则书Schema"""
        try:
            query = """
            MATCH (rs:RulebookSchema)
            WHERE rs.id = $schema_id
            DELETE rs
            """
            
            async with self.neo4j.session() as session:
                await session.run(query, {"schema_id": schema_id})
                
            self.logger.info(f"规则书Schema已从数据库删除: {schema_id}")
            return True
                
        except Exception as e:
            self.logger.error(f"从数据库删除Schema失败: {e}")
            return False
    
    async def list_schemas(self) -> List[Dict[str, Any]]:
        """列出数据库中所有规则书"""
        try:
            query = """
            MATCH (rs:RulebookSchema)
            RETURN rs
            ORDER BY rs.created_at DESC
            """
            
            async with self.neo4j.session() as session:
                result = await session.run(query)
                records = await result.data()
                
                schemas = []
                for record in records:
                    rs_data = record['rs']
                    schema_data = json.loads(rs_data['schema_data'])
                    
                    schemas.append({
                        'schema_id': rs_data['id'],
                        'name': schema_data.get('name', rs_data['id']),
                        'version': schema_data.get('version', '1.0.0'),
                        'author': schema_data.get('author', ''),
                        'description': schema_data.get('description', ''),
                        'game_system': schema_data.get('game_system', ''),
                        'created_at': rs_data['created_at'],
                        'entity_count': len(schema_data.get('entities', {})),
                        'is_active': rs_data['is_active']
                    })
                
                return schemas
                
        except Exception as e:
            self.logger.error(f"列出规则书失败: {e}")
            return []
    
    async def schema_exists(self, schema_id: str) -> bool:
        """检查规则书是否存在"""
        query = """
        MATCH (rs:RulebookSchema)
        WHERE rs.id = $schema_id
        RETURN count(rs) as exists
        """
        
        async with self.neo4j.session() as session:
            result = await session.run(query, {"schema_id": schema_id})
            records = await result.data()
            
            return records[0]['exists'] > 0 if records else False
    
    # 使用其他序列化方法
    _serialize_schema = FilesystemRulebookStorage._serialize_schema
    _deserialize_schema = FilesystemRulebookStorage._deserialize_schema
    _generate_schema_hash = FilesystemRulebookStorage._generate_schema_hash


# ==================== 规则书管理器 ====================

class RulebookManager:
    """规则书管理器
    
    协调规则书的上传、验证、激活和查询。
    支持规则书导入、导出和版本管理。
    """
    
    def __init__(
        self,
        storage: IRulebookStorage,
        schema_manager: Optional[SchemaManager] = None
    ):
        """
        初始化规则书管理器
        
        Args:
            storage: 规则书存储实现
            schema_manager: Schema管理器（可选）
        """
        self.storage = storage
        self.schema_manager = schema_manager or SchemaManager()
        self.logger = logging.getLogger(__name__)
        
        self._active_schema_id: Optional[str] = None
    
    async def upload_schema(
        self,
        schema_data: Dict[str, Any],
        uploader_id: str,
        validate: bool = True
    ) -> str:
        """
        上传并验证规则书
        
        Args:
            schema_data: 规则书JSON数据
            uploader_id: 上传者ID
            validate: 是否验证Schema（默认True）
            
        Returns:
            schema_id: 规则书ID
            
        Raises:
            ValidationError: Schema验证失败
            DataStorageError: 存储失败
        """
        try:
            # 验证Schema
            if validate:
                await self._validate_schema_data(schema_data)
            
            # 创建规则书Schema对象
            schema = RulebookSchema(
                schema_id=schema_data.get('schema_id'),
                name=schema_data.get('name'),
                version=schema_data.get('version', '1.0.0'),
                author=schema_data.get('author', ''),
                description=schema_data.get('description', ''),
                game_system=schema_data.get('game_system', ''),
                created_at=datetime.now()
            )
            
            # 检查Schema ID是否已存在
            existing_schema = await self.storage.load_schema(schema.schema_id)
            if existing_schema:
                raise ValidationError(f"规则书ID已存在: {schema.schema_id}")
            
            # 保存Schema
            schema_hash = await self.storage.save_schema(schema)
            
            self.logger.info(f"规则书上传统功: {schema.schema_id}")
            return schema.schema_id
            
        except Exception as e:
            logger.error(f"上传规则书失败: {e}")
            raise
    
    async def _validate_schema_data(self, schema_data: Dict[str, Any]) -> None:
        """验证规则书数据"""
        errors = []
        
        # 检查必需字段
        required_fields = ['schema_id', 'name', 'game_system', 'entities']
        for field in required_fields:
            if field not in schema_data:
                errors.append(f"缺少必需字段: {field}")
        
        # 验证实体定义
        entities = schema_data.get('entities', {})
        if not entities:
            errors.append("必须定义entities字段")
        
        for entity_id, entity_def in entities.items():
            if not entity_def.get('properties'):
                errors.append(f"实体{entity_id}必须定义properties字段")
        
        # 验证规则定义
        rules = schema_data.get('rules', {})
        for rule_id, rule_def in rules.items():
            if not rule_def.get('type'):
                errors.append(f"规则{rule_id}必须定义type字段")
        
        if errors:
            raise ValidationError(f"规则书数据验证失败: {', '.join(errors)}")
    
    async def download_schema(self, schema_id: str) -> Optional[Dict[str, Any]]:
        """
        下载规则书
        
        Args:
            schema_id: 规则书ID
            
        Returns:
            规则书JSON数据或None
        """
        try:
            schema = await self.storage.load_schema(schema_id)
            
            if not schema:
                raise ValidationError(f"规则书不存在: {schema_id}")
            
            # 返回Schema数据
            return self.storage._serialize_schema(schema)
            
        except Exception as e:
            logger.error(f"下载规则书失败: {schema_id}, 错误: {e}")
            raise
    
    async def activate_schema(self, schema_id: str, user_id: str) -> bool:
        """
        激活规则书
        
        Args:
            schema_id: 规则书ID
            user_id: 用户ID
            
        Returns:
            是否激活成功
        """
        try:
            # 检查Schema是否存在
            if not await self.storage.schema_exists(schema_id):
                raise ValidationError(f"规则书不存在: {schema_id}")
            
            # 加载Schema
            schema = await self.storage.load_schema(schema_id)
            
            if not schema:
                raise ValidationError(f"无法加载规则书: {schema_id}")
            
            # 设置为活跃Schema
            self._active_schema_id = schema_id
            self._update_active_schema(schema_id)
            
            self.logger.info(f"规则书已激活: {schema_id}")
            return True
            
        except Exception as e:
            logger.error(f"激活规则书失败: {schema_id}, 错误: {e}")
            return False
    
    async def _update_active_schema(self, schema_id: str) -> None:
        """更新活跃Schema状态"""
        # 在实际实现中，这可能需要在数据库中标记活跃Schema
        # 或者通过Session管理器设置当前Schema
        self._active_schema_id = schema_id
    
    async def get_active_schema(self) -> Optional[Dict[str, Any]]:
        """
        获取当前活跃的规则书
        
        Returns:
            活跃规则书信息或None
        """
        if not self._active_schema_id:
            return None
        
        schema = await self.storage.load_schema(self._active_schema_id)
        
        if schema:
            return self.storage._serialize_schema(schema)
        
        return None
    
    async def list_schemas(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有可用的规则书
        
        Args:
            user_id: 用户ID（可选，用于过滤）
            
        Returns:
            规则书列表
        """
        try:
            schemas = await self.storage.list_schemas()
            
            # 可以根据user_id过滤规则书
            if user_id:
                schemas = [s for s in schemas if s.get('uploader_id') == user_id]
            
            return schemas
            
        except Exception as e:
            logger.error(f"列出规则书失败: {e}")
            return []
    
    async def delete_schema(self, schema_id: str, user_id: str) -> bool:
        """
        删除规则书
        
        Args:
            schema_id: 规则书ID
            user_id: 删除者ID
            
        Returns:
            是否删除成功
        """
        try:
            # 验证删除权限（实际实现中应该添加权限检查）
            
            # 如果删除的是活跃Schema，清除活跃状态
            if self._active_schema_id == schema_id:
                self._active_schema_id = None
            
            # 从存储删除
            success = await self.storage.delete_schema(schema_id)
            
            if success:
                self.logger.info(f"规则书已删除: {schema_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"删除规则书失败: {schema_id}, 错误: {e}")
            return False
    
    async def validate_schema_for_session(
        self,
        session_id: str,
        schema_id: str
    ) -> Dict[str, Any]:
        """
        验证规则书是否适用于游戏会话
        
        Args:
            session_id: 游戏会话ID
            schema_id: 规则书ID
            
        Returns:
            验证结果 {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str]
            }
        """
        try:
            # 加载Schema
            schema = await self.storage.load_schema(schema_id)
            
            if not schema:
                return {
                    'valid': False,
                    'errors': [f"规则书不存在: {schema_id}"],
                    'warnings': []
                }
            
            # 验证Schema完整性
            errors = []
            warnings = []
            
            # 检查必需实体
            required_entities = ['Character', 'Skill', 'Item', 'GameSession']
            for entity_type in required_entities:
                if entity_type not in schema.entities:
                    errors.append(f"缺少必需实体: {entity_type}")
            
            return {
                'valid': len(errors) == 0,
                'errors': errors,
                'warnings': warnings
            }
            
        except Exception as e:
            logger.error(f"验证规则书失败: {e}")
            return {
                'valid': False,
                'errors': [str(e)],
                'warnings': []
            }
    
    async def export_schema(self, schema_id: str) -> Optional[str]:
        """
        导出规则书为JSON字符串
        
        Args:
            schema_id: 规则书ID
            
        Returns:
            JSON字符串或None
        """
        try:
            schema = await self.storage.load_schema(schema_id)
            
            if not schema:
                raise ValidationError(f"规则书不存在: {schema_id}")
            
            return json.dumps(self.storage._serialize_schema(schema), indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"导出规则书失败: {schema_id}, 错误: {e}")
            return None
    
    async def import_schema(self, schema_json: str, uploader_id: str) -> str:
        """
        导入规则书JSON
        
        Args:
            schema_json: 规则书JSON字符串
            uploader_id: 上传者ID
            
        Returns:
            规则书ID
        """
        try:
            # 解析JSON
            schema_data = json.loads(schema_json)
            
            # 上传Schema
            schema_id = await self.upload_schema(schema_data, uploader_id)
            
            self.logger.info(f"规则书导入成功: {schema_id}")
            return schema_id
            
        except json.JSONDecodeError as e:
            raise ValidationError(f"无效的JSON格式: {e}")
        except Exception as e:
            raise DataStorageError(f"导入规则书失败: {e}")
    
    def get_active_schema_id(self) -> Optional[str]:
        """获取当前活跃的Schema ID"""
        return self._active_schema_id


# 导出函数
__all__ = [
    "IRulebookStorage",
    "FilesystemRulebookStorage",
    "DatabaseRulebookStorage",
    "RulebookManager",
]