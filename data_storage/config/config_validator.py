"""
配置验证器实现

负责验证配置数据的正确性和完整性。
"""

import logging
from typing import Dict, Any, List, Optional, Union
from abc import ABC, abstractmethod

from ..interfaces import ValidationError

logger = logging.getLogger(__name__)


class IConfigValidator(ABC):
    """配置验证器接口"""
    
    @abstractmethod
    def validate_config(self, config_data: Dict[str, Any]) -> None:
        """验证完整配置"""
        pass
    
    @abstractmethod
    def validate_updates(self, updates: Dict[str, Any]) -> None:
        """验证配置更新"""
        pass


class ConfigValidator(IConfigValidator):
    """配置验证器实现"""
    
    def __init__(self):
        """初始化配置验证器"""
        self._required_fields = {
            'primary_backend': str,
            'backends': dict
        }
        
        self._optional_fields = {
            'cache_backend': (str, type(None)),
            'file_storage_backend': (str, type(None)),
            'instantiation': dict,
            'cache': dict,
            'enabled': bool
        }
        
        self._backend_required_fields = {
            'type': str,
            'config': dict
        }
        
        self._backend_optional_fields = {
            'enabled': bool
        }
        
        self._supported_backend_types = [
            'neo4j',
            'redis',
            'filesystem',
            'mongodb',
            'postgresql'
        ]
        
        logger.info("配置验证器初始化完成")
    
    def validate_config(self, config_data: Dict[str, Any]) -> None:
        """
        验证完整配置
        
        Args:
            config_data: 配置数据
            
        Raises:
            ValidationError: 配置验证失败
        """
        try:
            # 验证基础结构
            self._validate_basic_structure(config_data)
            
            # 验证必需字段
            self._validate_required_fields(config_data)
            
            # 验证可选字段类型
            self._validate_optional_fields(config_data)
            
            # 验证后端配置
            self._validate_backends(config_data.get('backends', {}))
            
            # 验证主后端引用
            self._validate_primary_backend(config_data)
            
            # 验证缓存后端引用
            self._validate_cache_backend(config_data)
            
            # 验证文件存储后端引用
            self._validate_file_storage_backend(config_data)
            
            # 验证实例化配置
            self._validate_instantiation_config(config_data.get('instantiation', {}))
            
            # 验证缓存配置
            self._validate_cache_config(config_data.get('cache', {}))
            
            logger.info("配置验证通过")
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            raise ValidationError(f"配置验证失败: {e}")
    
    def validate_updates(self, updates: Dict[str, Any]) -> None:
        """
        验证配置更新
        
        Args:
            updates: 更新的配置项
            
        Raises:
            ValidationError: 更新验证失败
        """
        try:
            # 验证更新字段
            for key, value in updates.items():
                if key in self._required_fields:
                    expected_type = self._required_fields[key]
                    if not isinstance(value, expected_type):
                        raise ValidationError(f"字段 {key} 类型错误，期望 {expected_type.__name__}")
                
                elif key in self._optional_fields:
                    expected_types = self._optional_fields[key]
                    if not isinstance(value, expected_types):
                        raise ValidationError(f"字段 {key} 类型错误，期望 {expected_types}")
                
                elif key == 'backends':
                    self._validate_backends(value)
                
                elif key == 'instantiation':
                    self._validate_instantiation_config(value)
                
                elif key == 'cache':
                    self._validate_cache_config(value)
                
                else:
                    logger.warning(f"未知的配置字段: {key}")
            
            logger.info("配置更新验证通过")
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"配置更新验证失败: {e}")
            raise ValidationError(f"配置更新验证失败: {e}")
    
    def _validate_basic_structure(self, config_data: Dict[str, Any]) -> None:
        """验证基础结构"""
        if not isinstance(config_data, dict):
            raise ValidationError("配置必须是字典类型")
    
    def _validate_required_fields(self, config_data: Dict[str, Any]) -> None:
        """验证必需字段"""
        missing_fields = []
        
        for field, expected_type in self._required_fields.items():
            if field not in config_data:
                missing_fields.append(field)
            elif not isinstance(config_data[field], expected_type):
                raise ValidationError(f"字段 {field} 类型错误，期望 {expected_type.__name__}")
        
        if missing_fields:
            raise ValidationError(f"缺少必需字段: {', '.join(missing_fields)}")
    
    def _validate_optional_fields(self, config_data: Dict[str, Any]) -> None:
        """验证可选字段类型"""
        for field, expected_types in self._optional_fields.items():
            if field in config_data:
                value = config_data[field]
                if not isinstance(value, expected_types):
                    type_names = [t.__name__ for t in expected_types if t is not type(None)]
                    raise ValidationError(f"字段 {field} 类型错误，期望 {' 或 '.join(type_names)}")
    
    def _validate_backends(self, backends: Dict[str, Any]) -> None:
        """验证后端配置"""
        if not isinstance(backends, dict):
            raise ValidationError("backends 必须是字典类型")
        
        if not backends:
            raise ValidationError("至少需要配置一个后端")
        
        for name, backend_config in backends.items():
            self._validate_single_backend(name, backend_config)
    
    def _validate_single_backend(self, name: str, backend_config: Dict[str, Any]) -> None:
        """验证单个后端配置"""
        if not isinstance(backend_config, dict):
            raise ValidationError(f"后端 {name} 配置必须是字典类型")
        
        # 验证必需字段
        for field, expected_type in self._backend_required_fields.items():
            if field not in backend_config:
                raise ValidationError(f"后端 {name} 缺少必需字段: {field}")
            elif not isinstance(backend_config[field], expected_type):
                raise ValidationError(f"后端 {name} 字段 {field} 类型错误，期望 {expected_type.__name__}")
        
        # 验证可选字段
        for field, expected_type in self._backend_optional_fields.items():
            if field in backend_config and not isinstance(backend_config[field], expected_type):
                raise ValidationError(f"后端 {name} 字段 {field} 类型错误，期望 {expected_type.__name__}")
        
        # 验证后端类型
        backend_type = backend_config.get('type')
        if backend_type not in self._supported_backend_types:
            raise ValidationError(f"不支持的后端类型: {backend_type}")
        
        # 验证后端特定配置
        self._validate_backend_specific_config(backend_type, backend_config.get('config', {}))
    
    def _validate_backend_specific_config(self, backend_type: str, config: Dict[str, Any]) -> None:
        """验证后端特定配置"""
        if backend_type == 'neo4j':
            self._validate_neo4j_config(config)
        elif backend_type == 'redis':
            self._validate_redis_config(config)
        elif backend_type == 'filesystem':
            self._validate_filesystem_config(config)
    
    def _validate_neo4j_config(self, config: Dict[str, Any]) -> None:
        """验证Neo4j配置"""
        required_fields = ['uri', 'username', 'password']
        
        for field in required_fields:
            if field not in config:
                raise ValidationError(f"Neo4j配置缺少必需字段: {field}")
        
        # 验证URI格式
        uri = config.get('uri', '')
        if not uri.startswith(('bolt://', 'neo4j://', 'http://', 'https://')):
            raise ValidationError("Neo4j URI格式无效")
    
    def _validate_redis_config(self, config: Dict[str, Any]) -> None:
        """验证Redis配置"""
        # Redis配置可以是简单的host:port，也可以是复杂配置
        if 'host' in config and 'port' in config:
            # 验证端口
            port = config.get('port')
            if not isinstance(port, int) or port <= 0 or port > 65535:
                raise ValidationError("Redis端口必须是1-65535之间的整数")
        
        # 如果是URI格式，验证URI
        if 'uri' in config:
            uri = config.get('uri', '')
            if not uri.startswith('redis://'):
                raise ValidationError("Redis URI格式无效")
    
    def _validate_filesystem_config(self, config: Dict[str, Any]) -> None:
        """验证文件系统配置"""
        if 'base_path' in config:
            base_path = config.get('base_path')
            if not isinstance(base_path, str):
                raise ValidationError("文件系统base_path必须是字符串")
    
    def _validate_primary_backend(self, config_data: Dict[str, Any]) -> None:
        """验证主后端引用"""
        primary_backend = config_data.get('primary_backend')
        backends = config_data.get('backends', {})
        
        if primary_backend not in backends:
            raise ValidationError(f"主后端 {primary_backend} 未在backends中定义")
    
    def _validate_cache_backend(self, config_data: Dict[str, Any]) -> None:
        """验证缓存后端引用"""
        cache_backend = config_data.get('cache_backend')
        
        if cache_backend is not None:
            backends = config_data.get('backends', {})
            if cache_backend not in backends:
                raise ValidationError(f"缓存后端 {cache_backend} 未在backends中定义")
            
            # 验证缓存后端类型
            backend_config = backends[cache_backend]
            backend_type = backend_config.get('type')
            
            if backend_type not in ['redis']:
                raise ValidationError(f"缓存后端类型 {backend_type} 不支持缓存功能")
    
    def _validate_file_storage_backend(self, config_data: Dict[str, Any]) -> None:
        """验证文件存储后端引用"""
        file_storage_backend = config_data.get('file_storage_backend')
        
        if file_storage_backend is not None:
            backends = config_data.get('backends', {})
            if file_storage_backend not in backends:
                raise ValidationError(f"文件存储后端 {file_storage_backend} 未在backends中定义")
            
            # 验证文件存储后端类型
            backend_config = backends[file_storage_backend]
            backend_type = backend_config.get('type')
            
            if backend_type not in ['filesystem']:
                raise ValidationError(f"文件存储后端类型 {backend_type} 不支持文件存储功能")
    
    def _validate_instantiation_config(self, instantiation_config: Dict[str, Any]) -> None:
        """验证实例化配置"""
        if not isinstance(instantiation_config, dict):
            raise ValidationError("实例化配置必须是字典类型")
        
        # 验证字段类型
        field_types = {
            'cache_ttl': int,
            'max_instances': int,
            'enable_validation': bool,
            'auto_cleanup': bool
        }
        
        for field, expected_type in field_types.items():
            if field in instantiation_config and not isinstance(instantiation_config[field], expected_type):
                raise ValidationError(f"实例化配置字段 {field} 类型错误，期望 {expected_type.__name__}")
        
        # 验证值范围
        if 'cache_ttl' in instantiation_config:
            ttl = instantiation_config['cache_ttl']
            if ttl < 0:
                raise ValidationError("cache_ttl 必须是非负整数")
        
        if 'max_instances' in instantiation_config:
            max_instances = instantiation_config['max_instances']
            if max_instances <= 0:
                raise ValidationError("max_instances 必须是正整数")
    
    def _validate_cache_config(self, cache_config: Dict[str, Any]) -> None:
        """验证缓存配置"""
        if not isinstance(cache_config, dict):
            raise ValidationError("缓存配置必须是字典类型")
        
        # 验证字段类型
        field_types = {
            'default_ttl': int,
            'max_memory_items': int,
            'eviction_strategy': str,
            'persistent_cache': bool,
            'write_strategy': str
        }
        
        for field, expected_type in field_types.items():
            if field in cache_config and not isinstance(cache_config[field], expected_type):
                raise ValidationError(f"缓存配置字段 {field} 类型错误，期望 {expected_type.__name__}")
        
        # 验证枚举值
        if 'eviction_strategy' in cache_config:
            strategy = cache_config['eviction_strategy']
            valid_strategies = ['lru', 'lfu', 'ttl']
            if strategy not in valid_strategies:
                raise ValidationError(f"无效的驱逐策略: {strategy}，支持: {', '.join(valid_strategies)}")
        
        if 'write_strategy' in cache_config:
            strategy = cache_config['write_strategy']
            valid_strategies = ['write_through', 'write_back']
            if strategy not in valid_strategies:
                raise ValidationError(f"无效的写入策略: {strategy}，支持: {', '.join(valid_strategies)}")
        
        # 验证值范围
        if 'default_ttl' in cache_config:
            ttl = cache_config['default_ttl']
            if ttl < 0:
                raise ValidationError("default_ttl 必须是非负整数")
        
        if 'max_memory_items' in cache_config:
            max_items = cache_config['max_memory_items']
            if max_items <= 0:
                raise ValidationError("max_memory_items 必须是正整数")


class ConfigValidatorBuilder:
    """配置验证器构建器"""
    
    def __init__(self):
        """初始化构建器"""
        self._validator = ConfigValidator()
    
    def with_backend_type(self, backend_type: str) -> 'ConfigValidatorBuilder':
        """添加支持的后端类型"""
        self._validator._supported_backend_types.append(backend_type)
        return self
    
    def with_required_field(self, field: str, field_type: type) -> 'ConfigValidatorBuilder':
        """添加必需字段"""
        self._validator._required_fields[field] = field_type
        return self
    
    def build(self) -> ConfigValidator:
        """构建配置验证器"""
        return self._validator


# 便利函数
def validate_config(config_data: Dict[str, Any]) -> None:
    """
    便利函数：验证配置
    
    Args:
        config_data: 配置数据
    """
    validator = ConfigValidator()
    validator.validate_config(config_data)


def validate_config_updates(updates: Dict[str, Any]) -> None:
    """
    便利函数：验证配置更新
    
    Args:
        updates: 更新的配置项
    """
    validator = ConfigValidator()
    validator.validate_updates(updates)