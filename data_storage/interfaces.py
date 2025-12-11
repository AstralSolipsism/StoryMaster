"""
数据存储层核心接口定义

遵循项目现有的接口驱动设计模式，提供高度解耦的存储抽象层。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Type, Tuple, Generic
from enum import Enum
from datetime import datetime


# ==================== 基础枚举 ====================

class StorageBackendType(Enum):
    """存储后端类型"""
    NEO4J = "neo4j"
    REDIS = "redis"
    FILESYSTEM = "filesystem"


class EntityType(Enum):
    """实体类型"""
    USER = "User"
    CHARACTER = "Character"
    SPELL_TEMPLATE = "SpellTemplate"
    SPELL_INSTANCE = "SpellInstance"
    ITEM_TEMPLATE = "ItemTemplate"
    ITEM_INSTANCE = "ItemInstance"
    NPC_TEMPLATE = "NPCTemplate"
    NPC_INSTANCE = "NPCInstance"
    SCENE_TEMPLATE = "SceneTemplate"
    SCENE_INSTANCE = "SceneInstance"
    GAME_SESSION = "GameSession"


class RecordType(Enum):
    """记录类型"""
    DIALOGUE = "dialogue"
    NARRATION = "narration"
    EVENT = "event"
    SYSTEM = "system"


# ==================== 基础数据结构 ====================

@dataclass
class Entity:
    """基础实体"""
    id: str
    entity_type: EntityType
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class EntityTemplate:
    """实体模板"""
    id: str
    entity_type: EntityType
    template_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    base_properties: Dict[str, Any] = field(default_factory=dict)
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class EntityInstance:
    """实体实例"""
    id: str
    entity_type: EntityType
    instance_id: str
    template_id: str
    template_type: EntityType
    properties: Dict[str, Any] = field(default_factory=dict)
    current_state: Dict[str, Any] = field(default_factory=dict)
    position: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Relationship:
    """关系"""
    id: str
    from_entity_id: str
    to_entity_id: str
    relationship_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class GameRecord:
    """游戏记录"""
    id: str
    session_id: str
    timestamp: datetime
    record_type: RecordType
    content: str
    sender: Optional[str] = None
    character: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DMPreferences:
    """DM偏好设置"""
    user_id: str
    dm_style: Dict[str, Any] = field(default_factory=dict)
    custom_prompts: Dict[str, str] = field(default_factory=dict)
    last_updated: Optional[datetime] = None


@dataclass
class EntityFilter:
    """实体过滤器"""
    entity_types: Optional[List[str]] = None
    name_pattern: Optional[str] = None
    property_filters: Optional[Dict[str, Any]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    order_by: Optional[str] = None
    order_desc: bool = False
    limit: Optional[int] = None
    offset: Optional[int] = None


@dataclass
class RelationshipFilter:
    """关系过滤器"""
    relationship_types: Optional[List[str]] = None
    source_ids: Optional[List[str]] = None
    target_ids: Optional[List[str]] = None
    name_pattern: Optional[str] = None
    property_filters: Optional[Dict[str, Any]] = None
    min_weight: Optional[float] = None
    max_weight: Optional[float] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    order_by: Optional[str] = None
    order_desc: bool = False
    limit: Optional[int] = None
    offset: Optional[int] = None


@dataclass
class QueryResult:
    """查询结果"""
    items: List[Any] = field(default_factory=list)
    total_count: int = 0
    has_more: bool = False


# ==================== 异常定义 ====================

class DataStorageError(Exception):
    """数据存储异常基类"""
    pass


class ValidationError(DataStorageError):
    """数据验证异常"""
    pass


# ==================== 存储适配器接口 ====================

class IStorageAdapter(ABC):
    """存储适配器接口"""
    
    @abstractmethod
    async def connect(self) -> bool:
        """连接存储"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """断开存储连接"""
        pass
    
    @abstractmethod
    async def execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """执行查询"""
        pass
    
    @abstractmethod
    async def execute_transaction(self, operations: List[Tuple[str, Dict[str, Any]]]) -> bool:
        """执行事务"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接状态"""
        pass


class ICacheManager(ABC):
    """缓存管理器接口"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存数据"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存数据"""
        pass
    
    @abstractmethod
    async def invalidate_pattern(self, pattern: str) -> int:
        """根据模式批量删除缓存"""
        pass
    
    @abstractmethod
    async def get_or_set(self, key: str, fetch_func, ttl: Optional[int] = None) -> Any:
        """获取缓存，如果不存在则调用fetch_func获取并缓存"""
        pass


class IFileStorage(ABC):
    """文件存储接口"""
    
    @abstractmethod
    async def read_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """读取文件"""
        pass
    
    @abstractmethod
    async def write_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """写入文件"""
        pass
    
    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """删除文件"""
        pass
    
    @abstractmethod
    async def list_files(self, directory: str, pattern: str = "*") -> List[str]:
        """列出目录中的文件"""
        pass
    
    @abstractmethod
    async def exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        pass


# ==================== 实例化管理接口 ====================

class IInstantiationManager(ABC):
    """实例化管理器接口"""
    
    @abstractmethod
    async def create_instance(self, template_id: str, instance_data: Dict[str, Any]) -> str:
        """基于模板创建实例"""
        pass
    
    @abstractmethod
    async def get_instance(self, instance_id: str) -> Optional[EntityInstance]:
        """获取实例"""
        pass
    
    @abstractmethod
    async def update_instance(self, instance_id: str, updates: Dict[str, Any]) -> bool:
        """更新实例"""
        pass
    
    @abstractmethod
    async def delete_instance(self, instance_id: str) -> bool:
        """删除实例"""
        pass
    
    @abstractmethod
    async def get_instances_by_template(self, template_id: str) -> List[EntityInstance]:
        """获取模板的所有实例"""
        pass
    
    @abstractmethod
    async def get_template(self, template_id: str) -> Optional[EntityTemplate]:
        """获取模板"""
        pass


# ==================== 数据访问接口 ====================

class IEntityRepository(ABC):
    """实体仓库接口"""
    
    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Optional[Entity]:
        """根据ID获取实体"""
        pass
    
    @abstractmethod
    async def create(self, entity_data: Dict[str, Any]) -> str:
        """创建实体"""
        pass
    
    @abstractmethod
    async def update(self, entity_id: str, updates: Dict[str, Any]) -> bool:
        """更新实体"""
        pass
    
    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """删除实体"""
        pass
    
    @abstractmethod
    async def search(self, filters: Dict[str, Any], limit: int = 50) -> List[Entity]:
        """搜索实体"""
        pass


class IRelationshipRepository(ABC):
    """关系仓库接口"""
    
    @abstractmethod
    async def create_relationship(self, from_entity: str, to_entity: str,
                                relation_type: str, properties: Dict[str, Any]) -> str:
        """创建关系"""
        pass
    
    @abstractmethod
    async def get_relationships(self, entity_id: str, 
                               relation_type: Optional[str] = None,
                               direction: str = "both") -> List[Relationship]:
        """获取实体的关系"""
        pass
    
    @abstractmethod
    async def update_relationship(self, relationship_id: str, updates: Dict[str, Any]) -> bool:
        """更新关系"""
        pass
    
    @abstractmethod
    async def delete_relationship(self, relationship_id: str) -> bool:
        """删除关系"""
        pass


class IGameRecordRepository(ABC):
    """游戏记录仓库接口"""
    
    @abstractmethod
    async def save_record(self, record: GameRecord) -> bool:
        """保存游戏记录"""
        pass
    
    @abstractmethod
    async def get_records(self, session_id: str, start_date: Optional[str] = None,
                        end_date: Optional[str] = None, limit: int = 100) -> List[GameRecord]:
        """获取游戏记录"""
        pass
    
    @abstractmethod
    async def get_records_by_type(self, session_id: str, record_type: RecordType,
                               limit: int = 50) -> List[GameRecord]:
        """根据类型获取游戏记录"""
        pass


class IDMPreferencesRepository(ABC):
    """DM偏好设置仓库接口"""
    
    @abstractmethod
    async def save_preferences(self, preferences: DMPreferences) -> bool:
        """保存DM偏好设置"""
        pass
    
    @abstractmethod
    async def get_preferences(self, user_id: str) -> Optional[DMPreferences]:
        """获取DM偏好设置"""
        pass
    
    @abstractmethod
    async def update_preferences(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """更新DM偏好设置"""
        pass


# ==================== 配置接口 ====================

@dataclass
class StorageBackendConfig:
    """存储后端配置"""
    backend_type: StorageBackendType
    connection_params: Dict[str, Any]
    pool_size: int = 10
    timeout: int = 30


@dataclass
class DataStorageConfig:
    """数据存储配置"""
    backends: Dict[StorageBackendType, StorageBackendConfig]
    default_ttl: int = 300
    cache_prefix: str = "storymaster"
    data_path: str = "./data"
    enable_backups: bool = True
    backup_interval: int = 3600  # 秒


class IDataStorageConfig(ABC):
    """数据存储配置管理接口"""
    
    @abstractmethod
    async def load_config(self) -> DataStorageConfig:
        """加载配置"""
        pass
    
    @abstractmethod
    async def save_config(self, config: DataStorageConfig) -> bool:
        """保存配置"""
        pass
    
    @abstractmethod
    async def validate_config(self, config: DataStorageConfig) -> Tuple[bool, List[str]]:
        """验证配置"""
        pass


class IStorageBackend(ABC):
    """存储后端接口"""
    
    @abstractmethod
    def get_backend_type(self) -> StorageBackendType:
        """获取后端类型"""
        pass
    
    @abstractmethod
    def get_adapter_class(self) -> Type[IStorageAdapter]:
        """获取适配器类"""
        pass
    
    @abstractmethod
    def get_config_schema(self) -> Dict[str, Any]:
            """获取配置模式"""
            pass
    
    
# ==================== 模板仓库接口 ====================

class ITemplateRepository(ABC):
    """模板仓库接口"""
    
    @abstractmethod
    async def get_by_id(self, template_id: str) -> Optional[EntityTemplate]:
        """根据ID获取模板"""
        pass
    
    @abstractmethod
    async def create(self, template: EntityTemplate) -> EntityTemplate:
        """创建模板"""
        pass
    
    @abstractmethod
    async def update(self, template: EntityTemplate) -> EntityTemplate:
        """更新模板"""
        pass
    
    @abstractmethod
    async def delete(self, template_id: str) -> bool:
        """删除模板"""
        pass
    
    @abstractmethod
    async def find(self, filters: 'TemplateFilter') -> QueryResult:
        """查找模板"""
        pass
    
    @abstractmethod
    async def find_by_entity_type(self, entity_type: str) -> List[EntityTemplate]:
        """根据实体类型查找模板"""
        pass
    
    @abstractmethod
    async def find_by_name(self, name: str) -> List[EntityTemplate]:
        """根据名称查找模板"""
        pass
    
    @abstractmethod
    async def search(self, search_term: str, limit: int = 10) -> List[EntityTemplate]:
        """搜索模板"""
        pass
    
    @abstractmethod
    async def count(self, filters: Optional['TemplateFilter'] = None) -> int:
        """统计模板数量"""
        pass


@dataclass
class TemplateFilter:
    """模板过滤器"""
    entity_types: Optional[List[str]] = None
    name_pattern: Optional[str] = None
    description_pattern: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    order_by: Optional[str] = None
    order_desc: bool = False
    limit: Optional[int] = None
    offset: Optional[int] = None


# ==================== 实例仓库接口 ====================

class IInstanceRepository(ABC):
    """实例仓库接口"""
    
    @abstractmethod
    async def get_by_id(self, instance_id: str) -> Optional[EntityInstance]:
        """根据ID获取实例"""
        pass
    
    @abstractmethod
    async def create(self, instance: EntityInstance) -> EntityInstance:
        """创建实例"""
        pass
    
    @abstractmethod
    async def update(self, instance: EntityInstance) -> EntityInstance:
        """更新实例"""
        pass
    
    @abstractmethod
    async def delete(self, instance_id: str) -> bool:
        """删除实例"""
        pass
    
    @abstractmethod
    async def find(self, filters: 'InstanceFilter') -> QueryResult:
        """查找实例"""
        pass
    
    @abstractmethod
    async def find_by_template_id(self, template_id: str) -> List[EntityInstance]:
        """根据模板ID查找实例"""
        pass
    
    @abstractmethod
    async def count(self, filters: Optional['InstanceFilter'] = None) -> int:
        """统计实例数量"""
        pass


@dataclass
class InstanceFilter:
    """实例过滤器"""
    template_ids: Optional[List[str]] = None
    entity_types: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    order_by: Optional[str] = None
    order_desc: bool = False
    limit: Optional[int] = None
    offset: Optional[int] = None


# ==================== 实例化管理相关数据结构 ====================

@dataclass
class InstantiationRule:
    """实例化规则"""
    id: str
    name: str
    description: Optional[str] = None
    source_type: str = ""
    target_type: str = ""
    conditions: Dict[str, Any] = field(default_factory=dict)
    transformations: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class InstantiationConfig:
    """实例化配置"""
    cache_ttl: int = 3600
    max_instances_per_template: int = 1000
    enable_validation: bool = True
    enable_rules: bool = True
    default_status: str = "active"


@dataclass
class CacheConfig:
    """缓存配置"""
    max_memory_items: int = 10000
    default_ttl: int = 300
    persistent_cache: bool = False
    eviction_strategy: str = "lru"
    write_strategy: str = "write_through"


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    current_size: int = 0
    hit_rate: float = 0.0
    memory_usage: int = 0  # 字节


@dataclass
class StorageBackend:
    """存储后端配置"""
    type: str
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 0