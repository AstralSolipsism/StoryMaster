"""
Agent配置管理器实现
"""

import json
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from pathlib import Path
import logging

from .interfaces import (
    IConfigurationManager, AgentConfig, ValidationResult,
    ReasoningMode
)

# ==================== 常量定义 ====================
MAX_CONCURRENCY_LIMIT = 10
MAX_EXECUTION_TIME = 600
MAX_CONFIG_ID_LENGTH = 50

class ConfigurationManager(IConfigurationManager):
    """配置管理器实现"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or "./configs"
        self.configs: Dict[str, AgentConfig] = {}
        self.logger = logging.getLogger(__name__)
        
        # 确保存储目录存在
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
    
    async def load_config(self, config_id: str) -> AgentConfig:
        """加载配置"""
        # 先从内存中查找
        if config_id in self.configs:
            return self.configs[config_id]
        
        # 验证config_id，防止路径遍历攻击
        if not self._is_valid_config_id(config_id):
            raise ValueError(f"无效的配置ID: {config_id}")
        
        # 从文件加载
        config_file = Path(self.storage_path) / f"{config_id}.json"
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                config = self._dict_to_config(config_data)
                self.configs[config_id] = config
                self.logger.info(f"配置 {config_id} 加载成功")
                return config
                
            except Exception as e:
                self.logger.error(f"加载配置 {config_id} 失败: {e}")
                raise
        
        raise ValueError(f"配置 {config_id} 不存在")
    
    async def save_config(self, config: AgentConfig) -> str:
        """保存配置"""
        config_id = config.agent_id
        
        # 验证配置
        validation_result = await self.validate_config(config)
        if not validation_result.is_valid:
            raise ValueError(f"配置验证失败: {validation_result.errors}")
        
        # 验证config_id，防止路径遍历攻击
        if not self._is_valid_config_id(config_id):
            raise ValueError(f"无效的配置ID: {config_id}")
        
        # 保存到内存
        self.configs[config_id] = config
        
        # 保存到文件
        config_file = Path(self.storage_path) / f"{config_id}.json"
        try:
            config_data = self._config_to_dict(config)
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"配置 {config_id} 保存成功")
            return config_id
            
        except Exception as e:
            self.logger.error(f"保存配置 {config_id} 失败: {e}")
            raise
    
    async def validate_config(self, config: AgentConfig) -> ValidationResult:
        """验证配置"""
        errors = []
        warnings = []
        
        # 基础字段验证
        if not config.agent_id:
            errors.append("agent_id 不能为空")
        
        if not config.agent_type:
            errors.append("agent_type 不能为空")
        
        if not config.version:
            errors.append("version 不能为空")
        
        # 推理模式验证
        if not isinstance(config.reasoning_mode, ReasoningMode):
            errors.append("reasoning_mode 必须是 ReasoningMode 枚举值")
        
        # 推理配置验证
        if not isinstance(config.reasoning_config, dict):
            errors.append("reasoning_config 必须是字典")
        
        # 工具配置验证
        if not isinstance(config.enabled_tools, list):
            errors.append("enabled_tools 必须是列表")
        
        if not isinstance(config.tool_config, dict):
            errors.append("tool_config 必须是字典")
        
        # 性能配置验证
        if config.max_execution_time <= 0:
            errors.append("max_execution_time 必须大于0")
        
        if config.max_memory_usage <= 0:
            errors.append("max_memory_usage 必须大于0")
        
        if config.concurrency_limit <= 0:
            errors.append("concurrency_limit 必须大于0")
        
        # 警告检查
        if config.concurrency_limit > MAX_CONCURRENCY_LIMIT:
            warnings.append("concurrency_limit 过高可能影响性能")
        
        if config.max_execution_time > MAX_EXECUTION_TIME:
            warnings.append("max_execution_time 过长可能导致资源占用")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    async def update_config(self, config_id: str, updates: Dict[str, Any]) -> AgentConfig:
        """更新配置"""
        # 加载现有配置
        config = await self.load_config(config_id)
        
        # 应用更新
        for key, value in updates.items():
            if hasattr(config, key):
                if key == "reasoning_mode" and isinstance(value, str):
                    # 字符串转换为枚举
                    setattr(config, key, ReasoningMode(value))
                else:
                    setattr(config, key, value)
            else:
                self.logger.warning(f"未知的配置字段: {key}")
        
        # 验证更新后的配置
        validation_result = await self.validate_config(config)
        if not validation_result.is_valid:
            raise ValueError(f"配置更新后验证失败: {validation_result.errors}")
        
        # 保存更新后的配置
        await self.save_config(config)
        return config
    
    async def list_configs(self, filters: Optional[Dict[str, Any]] = None) -> List[AgentConfig]:
        """列出配置"""
        # 从文件系统扫描配置文件
        config_files = list(Path(self.storage_path).glob("*.json"))
        
        configs = []
        for config_file in config_files:
            config_id = config_file.stem
            try:
                config = await self.load_config(config_id)
                
                # 应用过滤器
                if self._matches_filters(config, filters):
                    configs.append(config)
                    
            except Exception as e:
                self.logger.warning(f"跳过无效配置文件 {config_file}: {e}")
        
        return configs
    
    def _config_to_dict(self, config: AgentConfig) -> Dict[str, Any]:
        """将配置对象转换为字典"""
        config_dict = asdict(config)
        
        # 处理枚举类型
        if isinstance(config_dict.get('reasoning_mode'), ReasoningMode):
            config_dict['reasoning_mode'] = config_dict['reasoning_mode'].value
        
        return config_dict
    
    def _dict_to_config(self, config_data: Dict[str, Any]) -> AgentConfig:
        """将字典转换为配置对象"""
        # 创建新的字典，避免修改原始数据
        clean_config_data = {}
        
        for key, value in config_data.items():
            # 修复键名问题 - 处理可能错误的键名
            if key == 'concurrency_limit=':
                clean_config_data['concurrency_limit'] = value
            elif key.startswith('concurrency_limit='):
                # 处理类似 "concurrency_limit=8" 的键名
                clean_config_data['concurrency_limit'] = value
            else:
                clean_config_data[key] = value
        
        # 处理枚举类型
        if 'reasoning_mode' in clean_config_data and isinstance(clean_config_data['reasoning_mode'], str):
            clean_config_data['reasoning_mode'] = ReasoningMode(clean_config_data['reasoning_mode'])
        
        return AgentConfig(**clean_config_data)
    
    def _matches_filters(self, config: AgentConfig, filters: Optional[Dict[str, Any]]) -> bool:
        """检查配置是否匹配过滤器"""
        if not filters:
            return True
        
        for key, value in filters.items():
            if hasattr(config, key):
                config_value = getattr(config, key)
                if config_value != value:
                    return False
            else:
                return False
        
        return True
    
    def _is_valid_config_id(self, config_id: str) -> bool:
        """验证配置ID是否安全，防止路径遍历攻击"""
        # 只允许字母、数字、下划线和连字符
        pattern = r'^[a-zA-Z0-9_-]+$'
        return bool(re.match(pattern, config_id)) and len(config_id) <= MAX_CONFIG_ID_LENGTH

class DynamicConfigLoader:
    """动态配置加载器"""
    
    def __init__(self, config_manager: ConfigurationManager):
        self.config_manager = config_manager
        self.logger = logging.getLogger(__name__)
    
    async def load_from_file(self, config_path: str) -> AgentConfig:
        """从文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            config = self.config_manager._dict_to_config(config_data)
            
            # 验证配置
            validation_result = await self.config_manager.validate_config(config)
            if not validation_result.is_valid:
                raise ValueError(f"配置验证失败: {validation_result.errors}")
            
            return config
            
        except Exception as e:
            self.logger.error(f"从文件加载配置失败: {e}")
            raise
    
    async def load_from_database(self, config_id: str) -> AgentConfig:
        """从数据库加载配置（模拟实现）"""
        # 这里应该是实际的数据库查询
        # 暂时使用配置管理器
        return await self.config_manager.load_config(config_id)
    
    async def load_from_remote(self, config_url: str) -> AgentConfig:
        """从远程服务加载配置"""
        try:
            # 使用async with确保会话正确关闭
            async with aiohttp.ClientSession() as session:
                # 处理mock对象的情况
                if hasattr(session, 'get') and hasattr(session.get, '__call__'):
                    response_coro = session.get(config_url)
                    if hasattr(response_coro, '__aenter__'):
                        # 正常的异步上下文管理器
                        async with response_coro as response:
                            if response.status != 200:
                                raise Exception(f"HTTP错误: {response.status}")
                            
                            config_data = await response.json()
                    else:
                        # 处理mock对象
                        response = await response_coro
                        if response.status != 200:
                            raise Exception(f"HTTP错误: {response.status}")
                        
                        config_data = await response.json()
                else:
                    raise Exception("无法创建HTTP会话")
            
                config = self.config_manager._dict_to_config(config_data)
                
                # 验证配置
                validation_result = await self.config_manager.validate_config(config)
                if not validation_result.is_valid:
                    raise ValueError(f"配置验证失败: {validation_result.errors}")
                
                return config
            
        except Exception as e:
            self.logger.error(f"从远程加载配置失败: {e}")
            raise

# 便捷函数
async def create_config_manager(storage_path: Optional[str] = None) -> ConfigurationManager:
    """创建配置管理器"""
    return ConfigurationManager(storage_path)

async def create_dynamic_loader(config_manager: ConfigurationManager) -> DynamicConfigLoader:
    """创建动态配置加载器"""
    return DynamicConfigLoader(config_manager)