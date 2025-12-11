"""
管理器工厂实现

负责创建和配置管理器实例。
"""

import logging
from typing import Dict, Any, Optional, Type
from abc import ABC, abstractmethod

from ..interfaces import (
    IInstantiationManager,
    ICacheManager,
    IStorageAdapter,
    InstantiationConfig,
    CacheConfig,
    DataStorageError
)
from ..managers.instantiation_manager import InstantiationManager
from ..managers.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class IManagerFactory(ABC):
    """管理器工厂接口"""
    
    @abstractmethod
    def create_instantiation_manager(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None,
        config: Optional[InstantiationConfig] = None
    ) -> IInstantiationManager:
        """创建实例化管理器"""
        pass
    
    @abstractmethod
    def create_cache_manager(
        self,
        storage_adapter: IStorageAdapter,
        config: Optional[CacheConfig] = None
    ) -> ICacheManager:
        """创建缓存管理器"""
        pass


class ManagerFactory(IManagerFactory):
    """管理器工厂实现"""
    
    def __init__(self):
        """初始化管理器工厂"""
        self._instantiation_manager_class = InstantiationManager
        self._cache_manager_class = CacheManager
        
        logger.info("管理器工厂初始化完成")
    
    def create_instantiation_manager(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None,
        config: Optional[InstantiationConfig] = None
    ) -> IInstantiationManager:
        """
        创建实例化管理器
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器（可选）
            config: 实例化配置（可选）
            
        Returns:
            实例化管理器实例
        """
        try:
            manager = self._instantiation_manager_class(
                storage_adapter, cache_manager, config
            )
            logger.info("创建实例化管理器成功")
            return manager
            
        except Exception as e:
            logger.error(f"创建实例化管理器失败: {e}")
            raise DataStorageError(f"创建实例化管理器失败: {e}")
    
    def create_cache_manager(
        self,
        storage_adapter: IStorageAdapter,
        config: Optional[CacheConfig] = None
    ) -> ICacheManager:
        """
        创建缓存管理器
        
        Args:
            storage_adapter: 存储适配器
            config: 缓存配置（可选）
            
        Returns:
            缓存管理器实例
        """
        try:
            manager = self._cache_manager_class(storage_adapter, config)
            logger.info("创建缓存管理器成功")
            return manager
            
        except Exception as e:
            logger.error(f"创建缓存管理器失败: {e}")
            raise DataStorageError(f"创建缓存管理器失败: {e}")
    
    def register_instantiation_manager(self, manager_class: Type[IInstantiationManager]) -> None:
        """
        注册实例化管理器类
        
        Args:
            manager_class: 实例化管理器类
        """
        self._instantiation_manager_class = manager_class
        logger.info("注册实例化管理器类")
    
    def register_cache_manager(self, manager_class: Type[ICacheManager]) -> None:
        """
        注册缓存管理器类
        
        Args:
            manager_class: 缓存管理器类
        """
        self._cache_manager_class = manager_class
        logger.info("注册缓存管理器类")


class ManagerFactoryBuilder:
    """管理器工厂构建器"""
    
    def __init__(self):
        """初始化构建器"""
        self._factory = ManagerFactory()
    
    def with_instantiation_manager(self, manager_class: Type[IInstantiationManager]) -> 'ManagerFactoryBuilder':
        """设置实例化管理器类"""
        self._factory.register_instantiation_manager(manager_class)
        return self
    
    def with_cache_manager(self, manager_class: Type[ICacheManager]) -> 'ManagerFactoryBuilder':
        """设置缓存管理器类"""
        self._factory.register_cache_manager(manager_class)
        return self
    
    def build(self) -> ManagerFactory:
        """构建管理器工厂"""
        return self._factory


# 便利函数
def create_instantiation_manager(
    storage_adapter: IStorageAdapter,
    cache_manager: Optional[ICacheManager] = None,
    config: Optional[InstantiationConfig] = None
) -> IInstantiationManager:
    """
    便利函数：创建实例化管理器
    
    Args:
        storage_adapter: 存储适配器
        cache_manager: 缓存管理器（可选）
        config: 实例化配置（可选）
        
    Returns:
        实例化管理器实例
    """
    factory = ManagerFactory()
    return factory.create_instantiation_manager(storage_adapter, cache_manager, config)


def create_cache_manager(
    storage_adapter: IStorageAdapter,
    config: Optional[CacheConfig] = None
) -> ICacheManager:
    """
    便利函数：创建缓存管理器
    
    Args:
        storage_adapter: 存储适配器
        config: 缓存配置（可选）
        
    Returns:
        缓存管理器实例
    """
    factory = ManagerFactory()
    return factory.create_cache_manager(storage_adapter, config)