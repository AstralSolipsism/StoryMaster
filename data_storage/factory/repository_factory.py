"""
仓库工厂实现

负责创建和配置仓库实例。
"""

import logging
from typing import Dict, Any, Optional, Type
from abc import ABC, abstractmethod

from ..interfaces import (
    IEntityRepository,
    IRelationshipRepository,
    ITemplateRepository,
    IInstanceRepository,
    IStorageAdapter,
    ICacheManager,
    DataStorageError
)
from ..repositories.entity_repository import EntityRepository
from ..repositories.relationship_repository import RelationshipRepository
from ..repositories.template_repository import TemplateRepository
from ..repositories.instance_repository import InstanceRepository

logger = logging.getLogger(__name__)


class IRepositoryFactory(ABC):
    """仓库工厂接口"""
    
    @abstractmethod
    def create_entity_repository(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ) -> IEntityRepository:
        """创建实体仓库"""
        pass
    
    @abstractmethod
    def create_relationship_repository(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ) -> IRelationshipRepository:
        """创建关系仓库"""
        pass
    
    @abstractmethod
    def create_template_repository(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ) -> ITemplateRepository:
        """创建模板仓库"""
        pass
    
    @abstractmethod
    def create_instance_repository(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ) -> IInstanceRepository:
        """创建实例仓库"""
        pass


class RepositoryFactory(IRepositoryFactory):
    """仓库工厂实现"""
    
    def __init__(self):
        """初始化仓库工厂"""
        self._entity_repository_class = EntityRepository
        self._relationship_repository_class = RelationshipRepository
        self._template_repository_class = TemplateRepository
        self._instance_repository_class = InstanceRepository
        
        logger.info("仓库工厂初始化完成")
    
    def create_entity_repository(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ) -> IEntityRepository:
        """
        创建实体仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器（可选）
            
        Returns:
            实体仓库实例
        """
        try:
            repository = self._entity_repository_class(storage_adapter, cache_manager)
            logger.info("创建实体仓库成功")
            return repository
            
        except Exception as e:
            logger.error(f"创建实体仓库失败: {e}")
            raise DataStorageError(f"创建实体仓库失败: {e}")
    
    def create_relationship_repository(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ) -> IRelationshipRepository:
        """
        创建关系仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器（可选）
            
        Returns:
            关系仓库实例
        """
        try:
            repository = self._relationship_repository_class(storage_adapter, cache_manager)
            logger.info("创建关系仓库成功")
            return repository
            
        except Exception as e:
            logger.error(f"创建关系仓库失败: {e}")
            raise DataStorageError(f"创建关系仓库失败: {e}")
    
    def create_template_repository(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ) -> ITemplateRepository:
        """
        创建模板仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器（可选）
            
        Returns:
            模板仓库实例
        """
        try:
            repository = self._template_repository_class(storage_adapter, cache_manager)
            logger.info("创建模板仓库成功")
            return repository
            
        except Exception as e:
            logger.error(f"创建模板仓库失败: {e}")
            raise DataStorageError(f"创建模板仓库失败: {e}")
    
    def create_instance_repository(
        self,
        storage_adapter: IStorageAdapter,
        cache_manager: Optional[ICacheManager] = None
    ) -> IInstanceRepository:
        """
        创建实例仓库
        
        Args:
            storage_adapter: 存储适配器
            cache_manager: 缓存管理器（可选）
            
        Returns:
            实例仓库实例
        """
        try:
            repository = self._instance_repository_class(storage_adapter, cache_manager)
            logger.info("创建实例仓库成功")
            return repository
            
        except Exception as e:
            logger.error(f"创建实例仓库失败: {e}")
            raise DataStorageError(f"创建实例仓库失败: {e}")
    
    def register_entity_repository(self, repository_class: Type[IEntityRepository]) -> None:
        """
        注册实体仓库类
        
        Args:
            repository_class: 实体仓库类
        """
        self._entity_repository_class = repository_class
        logger.info("注册实体仓库类")
    
    def register_relationship_repository(self, repository_class: Type[IRelationshipRepository]) -> None:
        """
        注册关系仓库类
        
        Args:
            repository_class: 关系仓库类
        """
        self._relationship_repository_class = repository_class
        logger.info("注册关系仓库类")
    
    def register_template_repository(self, repository_class: Type[ITemplateRepository]) -> None:
        """
        注册模板仓库类
        
        Args:
            repository_class: 模板仓库类
        """
        self._template_repository_class = repository_class
        logger.info("注册模板仓库类")
    
    def register_instance_repository(self, repository_class: Type[IInstanceRepository]) -> None:
        """
        注册实例仓库类
        
        Args:
            repository_class: 实例仓库类
        """
        self._instance_repository_class = repository_class
        logger.info("注册实例仓库类")


class RepositoryFactoryBuilder:
    """仓库工厂构建器"""
    
    def __init__(self):
        """初始化构建器"""
        self._factory = RepositoryFactory()
    
    def with_entity_repository(self, repository_class: Type[IEntityRepository]) -> 'RepositoryFactoryBuilder':
        """设置实体仓库类"""
        self._factory.register_entity_repository(repository_class)
        return self
    
    def with_relationship_repository(self, repository_class: Type[IRelationshipRepository]) -> 'RepositoryFactoryBuilder':
        """设置关系仓库类"""
        self._factory.register_relationship_repository(repository_class)
        return self
    
    def with_template_repository(self, repository_class: Type[ITemplateRepository]) -> 'RepositoryFactoryBuilder':
        """设置模板仓库类"""
        self._factory.register_template_repository(repository_class)
        return self
    
    def with_instance_repository(self, repository_class: Type[IInstanceRepository]) -> 'RepositoryFactoryBuilder':
        """设置实例仓库类"""
        self._factory.register_instance_repository(repository_class)
        return self
    
    def build(self) -> RepositoryFactory:
        """构建仓库工厂"""
        return self._factory


# 便利函数
def create_entity_repository(
    storage_adapter: IStorageAdapter,
    cache_manager: Optional[ICacheManager] = None
) -> IEntityRepository:
    """
    便利函数：创建实体仓库
    
    Args:
        storage_adapter: 存储适配器
        cache_manager: 缓存管理器（可选）
        
    Returns:
        实体仓库实例
    """
    factory = RepositoryFactory()
    return factory.create_entity_repository(storage_adapter, cache_manager)


def create_relationship_repository(
    storage_adapter: IStorageAdapter,
    cache_manager: Optional[ICacheManager] = None
) -> IRelationshipRepository:
    """
    便利函数：创建关系仓库
    
    Args:
        storage_adapter: 存储适配器
        cache_manager: 缓存管理器（可选）
        
    Returns:
        关系仓库实例
    """
    factory = RepositoryFactory()
    return factory.create_relationship_repository(storage_adapter, cache_manager)


def create_template_repository(
    storage_adapter: IStorageAdapter,
    cache_manager: Optional[ICacheManager] = None
) -> ITemplateRepository:
    """
    便利函数：创建模板仓库
    
    Args:
        storage_adapter: 存储适配器
        cache_manager: 缓存管理器（可选）
        
    Returns:
        模板仓库实例
    """
    factory = RepositoryFactory()
    return factory.create_template_repository(storage_adapter, cache_manager)


def create_instance_repository(
    storage_adapter: IStorageAdapter,
    cache_manager: Optional[ICacheManager] = None
) -> IInstanceRepository:
    """
    便利函数：创建实例仓库
    
    Args:
        storage_adapter: 存储适配器
        cache_manager: 缓存管理器（可选）
        
    Returns:
        实例仓库实例
    """
    factory = RepositoryFactory()
    return factory.create_instance_repository(storage_adapter, cache_manager)