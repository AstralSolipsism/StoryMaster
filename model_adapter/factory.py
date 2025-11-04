from typing import Dict, Type, List, Optional
from dataclasses import dataclass

from .interfaces import IModelAdapter, ProviderConfig, ValidationResult
from .adapters.anthropic import AnthropicAdapter
from .adapters.openrouter import OpenRouterAdapter
from .adapters.ollama import OllamaAdapter

@dataclass
class AdapterInfo:
    """适配器信息"""
    adapter_class: Type[IModelAdapter]
    default_config: ProviderConfig
    is_dynamic: bool = False
    is_local: bool = False

class ModelAdapterFactory:
    """适配器工厂"""
    
    _registry: Dict[str, AdapterInfo] = {}
    
    @classmethod
    def register_adapter(
        cls,
        provider_name: str,
        adapter_class: Type[IModelAdapter],
        default_config: ProviderConfig,
        is_dynamic: bool = False,
        is_local: bool = False
    ) -> None:
        """注册适配器"""
        cls._registry[provider_name] = AdapterInfo(
            adapter_class=adapter_class,
            default_config=default_config,
            is_dynamic=is_dynamic,
            is_local=is_local
        )
    
    @classmethod
    def create_adapter(cls, provider_name: str, config: ProviderConfig) -> IModelAdapter:
        """创建适配器实例"""
        adapter_info = cls._registry.get(provider_name)
        if not adapter_info:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        # Merge default and user-provided config
        # Note: This is a shallow merge. A deep merge might be needed for nested configs.
        merged_config_dict = {**adapter_info.default_config, **config}
        merged_config = ProviderConfig(**merged_config_dict)
        
        return adapter_info.adapter_class(merged_config)
    
    @classmethod
    def get_registered_providers(cls) -> List[str]:
        """获取所有注册的提供商"""
        return list(cls._registry.keys())
    
    @classmethod
    def get_dynamic_providers(cls) -> List[str]:
        """获取动态提供商列表"""
        return [
            name for name, info in cls._registry.items() 
            if info.is_dynamic
        ]
    
    @classmethod
    def get_local_providers(cls) -> List[str]:
        """获取本地提供商列表"""
        return [
            name for name, info in cls._registry.items() 
            if info.is_local
        ]
    
    @classmethod
    def validate_config(cls, provider_name: str, config: ProviderConfig) -> ValidationResult:
        """验证提供商配置"""
        try:
            adapter = cls.create_adapter(provider_name, config)
            return adapter.validate_config(config)
        except Exception as error:
            return ValidationResult(
                is_valid=False,
                errors=[str(error)]
            )

# Register all adapters
def register_all_adapters():
    if 'anthropic' not in ModelAdapterFactory.get_registered_providers():
        ModelAdapterFactory.register_adapter(
            'anthropic',
            AnthropicAdapter,
            ProviderConfig(timeout=30, max_retries=3)
        )

    if 'openrouter' not in ModelAdapterFactory.get_registered_providers():
        ModelAdapterFactory.register_adapter(
            'openrouter',
            OpenRouterAdapter,
            ProviderConfig(timeout=30, max_retries=3),
            is_dynamic=True
        )

    if 'ollama' not in ModelAdapterFactory.get_registered_providers():
        ModelAdapterFactory.register_adapter(
            'ollama',
            OllamaAdapter,
            ProviderConfig(timeout=60, max_retries=1),
            is_local=True
        )

register_all_adapters()