"""
配置管理器实现

提供统一的配置管理功能，支持配置的加载、验证和访问。
"""

import logging
import json
import os
from typing import Dict, Any, Optional, Union
from pathlib import Path

from ..interfaces import (
    DataStorageConfig,
    StorageBackend,
    InstantiationConfig,
    CacheConfig,
    DataStorageError,
    ValidationError
)
from .config_loader import ConfigLoader
from .config_validator import ConfigValidator

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径（可选）
        """
        self._config_path = config_path
        self._config: Optional[DataStorageConfig] = None
        self._config_loader = ConfigLoader()
        self._config_validator = ConfigValidator()
        
        logger.info("配置管理器初始化完成")
    
    async def load_config(self, config_path: Optional[str] = None) -> DataStorageConfig:
        """
        加载配置
        
        Args:
            config_path: 配置文件路径（可选，覆盖初始化时的路径）
            
        Returns:
            数据存储配置
        """
        try:
            # 确定配置文件路径
            path = config_path or self._config_path
            
            if not path:
                # 尝试从环境变量获取
                path = os.getenv('DATA_STORAGE_CONFIG_PATH')
            
            if not path:
                # 使用默认路径
                path = self._get_default_config_path()
            
            # 加载配置
            config_data = await self._config_loader.load_config(path)
            
            # 验证配置
            self._config_validator.validate_config(config_data)
            
            # 创建配置对象
            self._config = self._create_config_from_data(config_data)
            
            logger.info(f"配置加载成功: {path}")
            return self._config
            
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            raise DataStorageError(f"配置加载失败: {e}")
    
    def get_config(self) -> DataStorageConfig:
        """
        获取当前配置
        
        Returns:
            数据存储配置
            
        Raises:
            DataStorageError: 配置未加载
        """
        if not self._config:
            raise DataStorageError("配置未加载，请先调用 load_config()")
        
        return self._config
    
    def get_storage_backend(self, backend_name: str) -> StorageBackend:
        """
        获取存储后端配置
        
        Args:
            backend_name: 后端名称
            
        Returns:
            存储后端配置
            
        Raises:
            DataStorageError: 后端不存在或配置未加载
        """
        config = self.get_config()
        
        if backend_name not in config.backends:
            raise DataStorageError(f"存储后端不存在: {backend_name}")
        
        return config.backends[backend_name]
    
    def get_primary_backend(self) -> StorageBackend:
        """
        获取主存储后端配置
        
        Returns:
            主存储后端配置
            
        Raises:
            DataStorageError: 主后端不存在或配置未加载
        """
        config = self.get_config()
        
        if not config.primary_backend:
            raise DataStorageError("未配置主存储后端")
        
        return self.get_storage_backend(config.primary_backend)
    
    def get_cache_backend(self) -> Optional[StorageBackend]:
        """
        获取缓存后端配置
        
        Returns:
            缓存后端配置或None
        """
        config = self.get_config()
        
        if not config.cache_backend:
            return None
        
        return self.get_storage_backend(config.cache_backend)
    
    def get_file_storage_backend(self) -> Optional[StorageBackend]:
        """
        获取文件存储后端配置
        
        Returns:
            文件存储后端配置或None
        """
        config = self.get_config()
        
        if not config.file_storage_backend:
            return None
        
        return self.get_storage_backend(config.file_storage_backend)
    
    async def save_config(self, config_path: Optional[str] = None) -> None:
        """
        保存配置到文件
        
        Args:
            config_path: 配置文件路径（可选）
        """
        try:
            if not self._config:
                raise DataStorageError("没有可保存的配置")
            
            path = config_path or self._config_path or self._get_default_config_path()
            
            # 转换为字典
            config_data = self._config_to_dict(self._config)
            
            # 保存配置
            await self._config_loader.save_config(config_data, path)
            
            logger.info(f"配置保存成功: {path}")
            
        except Exception as e:
            logger.error(f"配置保存失败: {e}")
            raise DataStorageError(f"配置保存失败: {e}")
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """
        更新配置
        
        Args:
            updates: 更新的配置项
        """
        try:
            if not self._config:
                raise DataStorageError("配置未加载，无法更新")
            
            # 验证更新
            self._config_validator.validate_updates(updates)
            
            # 应用更新
            self._apply_updates(self._config, updates)
            
            logger.info("配置更新成功")
            
        except Exception as e:
            logger.error(f"配置更新失败: {e}")
            raise DataStorageError(f"配置更新失败: {e}")
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        # 尝试多个默认位置
        possible_paths = [
            "data_storage_config.json",
            "config/data_storage_config.json",
            os.path.expanduser("~/.data_storage/config.json"),
            "/etc/data_storage/config.json"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # 如果都不存在，返回第一个作为默认
        return possible_paths[0]
    
    def _create_config_from_data(self, config_data: Dict[str, Any]) -> DataStorageConfig:
        """从配置数据创建配置对象"""
        # 创建存储后端
        backends = {}
        for name, backend_data in config_data.get('backends', {}).items():
            backends[name] = StorageBackend(
                type=backend_data['type'],
                config=backend_data['config'],
                enabled=backend_data.get('enabled', True)
            )
        
        # 创建实例化配置
        instantiation_data = config_data.get('instantiation', {})
        instantiation_config = InstantiationConfig(
            cache_ttl=instantiation_data.get('cache_ttl', 3600),
            max_instances=instantiation_data.get('max_instances', 1000),
            enable_validation=instantiation_data.get('enable_validation', True),
            auto_cleanup=instantiation_data.get('auto_cleanup', True)
        )
        
        # 创建缓存配置
        cache_data = config_data.get('cache', {})
        cache_config = CacheConfig(
            default_ttl=cache_data.get('default_ttl', 3600),
            max_memory_items=cache_data.get('max_memory_items', 10000),
            eviction_strategy=cache_data.get('eviction_strategy', 'lru'),
            persistent_cache=cache_data.get('persistent_cache', False),
            write_strategy=cache_data.get('write_strategy', 'write_through')
        )
        
        return DataStorageConfig(
            primary_backend=config_data.get('primary_backend'),
            cache_backend=config_data.get('cache_backend'),
            file_storage_backend=config_data.get('file_storage_backend'),
            backends=backends,
            instantiation=instantiation_config,
            cache=cache_config,
            enabled=config_data.get('enabled', True)
        )
    
    def _config_to_dict(self, config: DataStorageConfig) -> Dict[str, Any]:
        """将配置对象转换为字典"""
        # 转换存储后端
        backends = {}
        for name, backend in config.backends.items():
            backends[name] = {
                'type': backend.type,
                'config': backend.config,
                'enabled': backend.enabled
            }
        
        # 转换实例化配置
        instantiation = {
            'cache_ttl': config.instantiation.cache_ttl,
            'max_instances': config.instantiation.max_instances,
            'enable_validation': config.instantiation.enable_validation,
            'auto_cleanup': config.instantiation.auto_cleanup
        }
        
        # 转换缓存配置
        cache = {
            'default_ttl': config.cache.default_ttl,
            'max_memory_items': config.cache.max_memory_items,
            'eviction_strategy': config.cache.eviction_strategy,
            'persistent_cache': config.cache.persistent_cache,
            'write_strategy': config.cache.write_strategy
        }
        
        return {
            'primary_backend': config.primary_backend,
            'cache_backend': config.cache_backend,
            'file_storage_backend': config.file_storage_backend,
            'backends': backends,
            'instantiation': instantiation,
            'cache': cache,
            'enabled': config.enabled
        }
    
    def _apply_updates(self, config: DataStorageConfig, updates: Dict[str, Any]) -> None:
        """应用配置更新"""
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                logger.warning(f"未知的配置项: {key}")


# 便利函数
async def load_config(config_path: Optional[str] = None) -> DataStorageConfig:
    """
    便利函数：加载配置
    
    Args:
        config_path: 配置文件路径（可选）
        
    Returns:
        数据存储配置
    """
    manager = ConfigManager(config_path)
    return await manager.load_config()


def get_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """
    便利函数：获取配置管理器
    
    Args:
        config_path: 配置文件路径（可选）
        
    Returns:
        配置管理器实例
    """
    return ConfigManager(config_path)