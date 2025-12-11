"""
存储工厂实现

负责创建和配置存储适配器实例。
"""

import logging
from typing import Dict, Any, Optional, Type
from abc import ABC, abstractmethod

from ..interfaces import (
    IStorageAdapter,
    ICacheManager,
    IFileStorage,
    StorageBackend,
    DataStorageConfig,
    DataStorageError
)
from ..adapters.neo4j_adapter import Neo4jAdapter
from ..adapters.redis_adapter import RedisAdapter
from ..adapters.filesystem_adapter import FileSystemAdapter

logger = logging.getLogger(__name__)


class IStorageFactory(ABC):
    """存储工厂接口"""
    
    @abstractmethod
    async def create_storage_adapter(
        self,
        backend: StorageBackend,
        config: DataStorageConfig
    ) -> IStorageAdapter:
        """创建存储适配器"""
        pass
    
    @abstractmethod
    async def create_cache_manager(
        self,
        backend: StorageBackend,
        config: DataStorageConfig
    ) -> ICacheManager:
        """创建缓存管理器"""
        pass
    
    @abstractmethod
    async def create_file_storage(
        self,
        backend: StorageBackend,
        config: DataStorageConfig
    ) -> IFileStorage:
        """创建文件存储"""
        pass


class StorageFactory(IStorageFactory):
    """存储工厂实现"""
    
    def __init__(self):
        """初始化存储工厂"""
        self._adapter_registry: Dict[str, Type[IStorageAdapter]] = {
            'neo4j': Neo4jAdapter,
            'redis': RedisAdapter,
            'filesystem': FileSystemAdapter
        }
        
        self._cache_registry: Dict[str, Type[ICacheManager]] = {
            'redis': RedisAdapter
        }
        
        self._file_storage_registry: Dict[str, Type[IFileStorage]] = {
            'filesystem': FileSystemAdapter
        }
        
        logger.info("存储工厂初始化完成")
    
    async def create_storage_adapter(
        self,
        backend: StorageBackend,
        config: DataStorageConfig
    ) -> IStorageAdapter:
        """
        创建存储适配器
        
        Args:
            backend: 存储后端配置
            config: 数据存储配置
            
        Returns:
            存储适配器实例
        """
        try:
            adapter_type = backend.type.lower()
            
            if adapter_type not in self._adapter_registry:
                raise DataStorageError(f"不支持的存储适配器类型: {adapter_type}")
            
            adapter_class = self._adapter_registry[adapter_type]
            
            # 创建适配器实例
            adapter = adapter_class(backend.config)
            
            # 初始化适配器
            await adapter.initialize()
            
            logger.info(f"创建存储适配器成功: {adapter_type}")
            return adapter
            
        except Exception as e:
            logger.error(f"创建存储适配器失败: {e}")
            raise DataStorageError(f"创建存储适配器失败: {e}")
    
    async def create_cache_manager(
        self,
        backend: StorageBackend,
        config: DataStorageConfig
    ) -> ICacheManager:
        """
        创建缓存管理器
        
        Args:
            backend: 存储后端配置
            config: 数据存储配置
            
        Returns:
            缓存管理器实例
        """
        try:
            cache_type = backend.type.lower()
            
            if cache_type not in self._cache_registry:
                raise DataStorageError(f"不支持的缓存管理器类型: {cache_type}")
            
            cache_class = self._cache_registry[cache_type]
            
            # 创建缓存管理器实例
            cache_manager = cache_class(backend.config)
            
            # 初始化缓存管理器
            await cache_manager.initialize()
            
            logger.info(f"创建缓存管理器成功: {cache_type}")
            return cache_manager
            
        except Exception as e:
            logger.error(f"创建缓存管理器失败: {e}")
            raise DataStorageError(f"创建缓存管理器失败: {e}")
    
    async def create_file_storage(
        self,
        backend: StorageBackend,
        config: DataStorageConfig
    ) -> IFileStorage:
        """
        创建文件存储
        
        Args:
            backend: 存储后端配置
            config: 数据存储配置
            
        Returns:
            文件存储实例
        """
        try:
            storage_type = backend.type.lower()
            
            if storage_type not in self._file_storage_registry:
                raise DataStorageError(f"不支持的文件存储类型: {storage_type}")
            
            storage_class = self._file_storage_registry[storage_type]
            
            # 创建文件存储实例
            file_storage = storage_class(backend.config)
            
            # 初始化文件存储
            await file_storage.initialize()
            
            logger.info(f"创建文件存储成功: {storage_type}")
            return file_storage
            
        except Exception as e:
            logger.error(f"创建文件存储失败: {e}")
            raise DataStorageError(f"创建文件存储失败: {e}")
    
    def register_adapter(
        self,
        adapter_type: str,
        adapter_class: Type[IStorageAdapter]
    ) -> None:
        """
        注册存储适配器类型
        
        Args:
            adapter_type: 适配器类型名称
            adapter_class: 适配器类
        """
        self._adapter_registry[adapter_type.lower()] = adapter_class
        logger.info(f"注册存储适配器: {adapter_type}")
    
    def register_cache_manager(
        self,
        cache_type: str,
        cache_class: Type[ICacheManager]
    ) -> None:
        """
        注册缓存管理器类型
        
        Args:
            cache_type: 缓存类型名称
            cache_class: 缓存管理器类
        """
        self._cache_registry[cache_type.lower()] = cache_class
        logger.info(f"注册缓存管理器: {cache_type}")
    
    def register_file_storage(
        self,
        storage_type: str,
        storage_class: Type[IFileStorage]
    ) -> None:
        """
        注册文件存储类型
        
        Args:
            storage_type: 存储类型名称
            storage_class: 文件存储类
        """
        self._file_storage_registry[storage_type.lower()] = storage_class
        logger.info(f"注册文件存储: {storage_type}")
    
    def get_supported_adapter_types(self) -> list[str]:
        """获取支持的适配器类型列表"""
        return list(self._adapter_registry.keys())
    
    def get_supported_cache_types(self) -> list[str]:
        """获取支持的缓存类型列表"""
        return list(self._cache_registry.keys())
    
    def get_supported_file_storage_types(self) -> list[str]:
        """获取支持的文件存储类型列表"""
        return list(self._file_storage_registry.keys())


class StorageFactoryBuilder:
    """存储工厂构建器"""
    
    def __init__(self):
        """初始化构建器"""
        self._factory = StorageFactory()
    
    def with_adapter(
        self,
        adapter_type: str,
        adapter_class: Type[IStorageAdapter]
    ) -> 'StorageFactoryBuilder':
        """添加适配器"""
        self._factory.register_adapter(adapter_type, adapter_class)
        return self
    
    def with_cache_manager(
        self,
        cache_type: str,
        cache_class: Type[ICacheManager]
    ) -> 'StorageFactoryBuilder':
        """添加缓存管理器"""
        self._factory.register_cache_manager(cache_type, cache_class)
        return self
    
    def with_file_storage(
        self,
        storage_type: str,
        storage_class: Type[IFileStorage]
    ) -> 'StorageFactoryBuilder':
        """添加文件存储"""
        self._factory.register_file_storage(storage_type, storage_class)
        return self
    
    def build(self) -> StorageFactory:
        """构建存储工厂"""
        return self._factory


# 便利函数
async def create_storage_adapter(
    backend: StorageBackend,
    config: DataStorageConfig
) -> IStorageAdapter:
    """
    便利函数：创建存储适配器
    
    Args:
        backend: 存储后端配置
        config: 数据存储配置
        
    Returns:
        存储适配器实例
    """
    factory = StorageFactory()
    return await factory.create_storage_adapter(backend, config)


async def create_cache_manager(
    backend: StorageBackend,
    config: DataStorageConfig
) -> ICacheManager:
    """
    便利函数：创建缓存管理器
    
    Args:
        backend: 存储后端配置
        config: 数据存储配置
        
    Returns:
        缓存管理器实例
    """
    factory = StorageFactory()
    return await factory.create_cache_manager(backend, config)


async def create_file_storage(
    backend: StorageBackend,
    config: DataStorageConfig
) -> IFileStorage:
    """
    便利函数：创建文件存储
    
    Args:
        backend: 存储后端配置
        config: 数据存储配置
        
    Returns:
        文件存储实例
    """
    factory = StorageFactory()
    return await factory.create_file_storage(backend, config)