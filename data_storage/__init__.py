"""
StoryMaster 数据存储层

该模块提供了基于Neo4j+Redis+文件系统的混合存储架构，支持：
- 实体原型与实例管理
- 高性能缓存
- 游戏记录存储
- DM偏好设置
- 插件化扩展
"""

from .interfaces import (
    # 存储适配器接口
    IStorageAdapter,
    ICacheManager,
    IFileStorage,
    
    # 实例化管理接口
    IInstantiationManager,
    
    # 数据访问接口
    IEntityRepository,
    IRelationshipRepository,
    IGameRecordRepository,
    IDMPreferencesRepository,
    
    # 数据模型
    Entity,
    EntityTemplate,
    EntityInstance,
    Relationship,
    GameRecord,
    DMPreferences,
    
    # 配置接口
    IDataStorageConfig,
    IStorageBackend,
)

from .adapters import (
    # Neo4j适配器
    Neo4jAdapter,
    
    # Redis适配器
    RedisAdapter,
    
    # 文件系统适配器
    FileSystemAdapter,
)

from .repositories import (
    # 实体仓库
    EntityRepository,
    TemplateRepository,
    InstanceRepository,
    
    # 关系仓库
    RelationshipRepository,
)

from .managers import (
    # 实例化管理器
    InstantiationManager,
    
    # 缓存管理器
    CacheManager,
)

from .factory import (
    # 存储工厂
    StorageFactory,
    RepositoryFactory,
)

from .interfaces import (
    # 配置数据类
    DataStorageConfig,
    StorageBackendConfig,
)

__version__ = "1.0.0"
__all__ = [
    # 接口
    "IStorageAdapter",
    "ICacheManager",
    "IFileStorage",
    "IInstantiationManager",
    "IEntityRepository",
    "IRelationshipRepository",
    "IGameRecordRepository",
    "IDMPreferencesRepository",
    "Entity",
    "EntityTemplate",
    "EntityInstance",
    "Relationship",
    "GameRecord",
    "DMPreferences",
    "IDataStorageConfig",
    "IStorageBackend",
    
    # 适配器
    "Neo4jAdapter",
    "RedisAdapter",
    "FileSystemAdapter",
    
    # 仓库
    "EntityRepository",
    "TemplateRepository",
    "InstanceRepository",
    "RelationshipRepository",
    
    # 管理器
    "InstantiationManager",
    "CacheManager",
    
    # 工厂
    "StorageFactory",
    "RepositoryFactory",
    
    # 配置
    "DataStorageConfig",
    "StorageBackendConfig",
]