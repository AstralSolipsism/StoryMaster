"""
配置加载器实现

负责从不同来源加载配置数据。
"""

import json
import yaml
import os
import logging
from typing import Dict, Any, Optional, Union
from pathlib import Path
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class IConfigLoader(ABC):
    """配置加载器接口"""
    
    @abstractmethod
    async def load_config(self, path: str) -> Dict[str, Any]:
        """加载配置"""
        pass
    
    @abstractmethod
    async def save_config(self, config_data: Dict[str, Any], path: str) -> None:
        """保存配置"""
        pass


class ConfigLoader(IConfigLoader):
    """配置加载器实现"""
    
    def __init__(self):
        """初始化配置加载器"""
        self._supported_formats = {
            '.json': self._load_json,
            '.yaml': self._load_yaml,
            '.yml': self._load_yaml
        }
        
        self._save_formats = {
            '.json': self._save_json,
            '.yaml': self._save_yaml,
            '.yml': self._save_yaml
        }
        
        logger.info("配置加载器初始化完成")
    
    async def load_config(self, path: str) -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            path: 配置文件路径
            
        Returns:
            配置数据字典
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式不支持
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(path):
                raise FileNotFoundError(f"配置文件不存在: {path}")
            
            # 获取文件扩展名
            file_ext = Path(path).suffix.lower()
            
            # 检查格式是否支持
            if file_ext not in self._supported_formats:
                raise ValueError(f"不支持的配置文件格式: {file_ext}")
            
            # 加载配置
            config_data = await self._supported_formats[file_ext](path)
            
            logger.info(f"配置文件加载成功: {path}")
            return config_data
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
    
    async def save_config(self, config_data: Dict[str, Any], path: str) -> None:
        """
        保存配置文件
        
        Args:
            config_data: 配置数据字典
            path: 配置文件路径
            
        Raises:
            ValueError: 文件格式不支持
        """
        try:
            # 获取文件扩展名
            file_ext = Path(path).suffix.lower()
            
            # 检查格式是否支持
            if file_ext not in self._save_formats:
                raise ValueError(f"不支持的配置文件格式: {file_ext}")
            
            # 确保目录存在
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # 保存配置
            await self._save_formats[file_ext](config_data, path)
            
            logger.info(f"配置文件保存成功: {path}")
            
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            raise
    
    async def load_from_env(self, prefix: str = "DATA_STORAGE_") -> Dict[str, Any]:
        """
        从环境变量加载配置
        
        Args:
            prefix: 环境变量前缀
            
        Returns:
            配置数据字典
        """
        try:
            config_data = {}
            
            # 遍历所有环境变量
            for key, value in os.environ.items():
                if key.startswith(prefix):
                    # 移除前缀并转换为小写
                    config_key = key[len(prefix):].lower()
                    
                    # 尝试解析值
                    parsed_value = self._parse_env_value(value)
                    config_data[config_key] = parsed_value
            
            logger.info(f"从环境变量加载配置成功，共 {len(config_data)} 项")
            return config_data
            
        except Exception as e:
            logger.error(f"从环境变量加载配置失败: {e}")
            raise
    
    async def load_from_dict(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        从字典加载配置
        
        Args:
            config_dict: 配置字典
            
        Returns:
            配置数据字典
        """
        try:
            # 深拷贝配置
            config_data = json.loads(json.dumps(config_dict))
            
            logger.info("从字典加载配置成功")
            return config_data
            
        except Exception as e:
            logger.error(f"从字典加载配置失败: {e}")
            raise
    
    async def merge_configs(
        self,
        base_config: Dict[str, Any],
        override_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        合并配置
        
        Args:
            base_config: 基础配置
            override_config: 覆盖配置
            
        Returns:
            合并后的配置
        """
        try:
            merged_config = self._deep_merge(base_config, override_config)
            
            logger.info("配置合并成功")
            return merged_config
            
        except Exception as e:
            logger.error(f"配置合并失败: {e}")
            raise
    
    async def _load_json(self, path: str) -> Dict[str, Any]:
        """加载JSON配置文件"""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    async def _load_yaml(self, path: str) -> Dict[str, Any]:
        """加载YAML配置文件"""
        try:
            import yaml
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            raise ImportError("需要安装PyYAML库来支持YAML配置文件")
    
    async def _save_json(self, config_data: Dict[str, Any], path: str) -> None:
        """保存JSON配置文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
    
    async def _save_yaml(self, config_data: Dict[str, Any], path: str) -> None:
        """保存YAML配置文件"""
        try:
            import yaml
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        except ImportError:
            raise ImportError("需要安装PyYAML库来支持YAML配置文件")
    
    def _parse_env_value(self, value: str) -> Union[str, int, float, bool, Dict[str, Any]]:
        """解析环境变量值"""
        # 尝试解析为JSON
        if value.startswith('{') and value.endswith('}'):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        # 尝试解析为布尔值
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # 尝试解析为数字
        try:
            if '.' in value:
                return float(value)
            else:
                return int(value)
        except ValueError:
            pass
        
        # 返回字符串
        return value
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并字典"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result


class ConfigLoaderBuilder:
    """配置加载器构建器"""
    
    def __init__(self):
        """初始化构建器"""
        self._loader = ConfigLoader()
    
    def with_format(self, file_ext: str, load_func, save_func) -> 'ConfigLoaderBuilder':
        """添加自定义格式支持"""
        self._loader._supported_formats[file_ext.lower()] = load_func
        self._loader._save_formats[file_ext.lower()] = save_func
        return self
    
    def build(self) -> ConfigLoader:
        """构建配置加载器"""
        return self._loader


# 便利函数
async def load_config_file(path: str) -> Dict[str, Any]:
    """
    便利函数：加载配置文件
    
    Args:
        path: 配置文件路径
        
    Returns:
        配置数据字典
    """
    loader = ConfigLoader()
    return await loader.load_config(path)


async def save_config_file(config_data: Dict[str, Any], path: str) -> None:
    """
    便利函数：保存配置文件
    
    Args:
        config_data: 配置数据字典
        path: 配置文件路径
    """
    loader = ConfigLoader()
    await loader.save_config(config_data, path)


async def load_config_from_env(prefix: str = "DATA_STORAGE_") -> Dict[str, Any]:
    """
    便利函数：从环境变量加载配置
    
    Args:
        prefix: 环境变量前缀
        
    Returns:
        配置数据字典
    """
    loader = ConfigLoader()
    return await loader.load_from_env(prefix)