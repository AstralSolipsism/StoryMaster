from typing import Dict, Optional

try:
    from core.config import settings
except ImportError:
    from StoryMaster.core.config import settings

from .entities import ProviderConfig
from .manager import ProviderManager, ProviderManagerConfig
from .profile_manager import ProviderProfileManager


def _build_default_provider_configs() -> Dict[str, ProviderConfig]:
    return {
        "openai_chat_completion": {
            "api_key": settings.openai_api_key,
            "openai_base_url": settings.openai_base_url,
            "timeout": 30,
            "max_retries": 3,
        },
        "openai_compatible_chat_completion": {
            "api_key": settings.openai_compatible_api_key,
            "openai_compatible_base_url": settings.openai_compatible_base_url,
            "timeout": 30,
            "max_retries": 3,
        },
        "groq_chat_completion": {
            "api_key": settings.groq_api_key,
            "groq_base_url": settings.groq_base_url,
            "timeout": 30,
            "max_retries": 3,
        },
        "zhipu_chat_completion": {
            "api_key": settings.zhipu_api_key,
            "zhipu_base_url": settings.zhipu_base_url,
            "timeout": 30,
            "max_retries": 3,
        },
        "anthropic_chat_completion": {
            "api_key": settings.anthropic_api_key,
            "anthropic_base_url": None,
            "timeout": 30,
            "max_retries": 3,
        },
        "openrouter_chat_completion": {
            "api_key": settings.openrouter_api_key,
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "timeout": 30,
            "max_retries": 3,
        },
        "ollama_chat_completion": {
            "ollama_base_url": settings.ollama_base_url,
            "timeout": 60,
            "max_retries": 1,
        },
    }


def create_provider_manager(
    profile_storage_path: Optional[str] = None,
) -> ProviderManager:
    provider_configs: Dict[str, ProviderConfig] = _build_default_provider_configs()
    default_provider = "openai_chat_completion"

    profile_manager = ProviderProfileManager(profile_storage_path)
    active_profile = profile_manager.get_active_profile()
    if active_profile:
        provider_configs = profile_manager.build_provider_config(active_profile)
        default_provider = active_profile.provider_type
    else:
        provider_configs = {}

    config = ProviderManagerConfig(
        default_provider=default_provider,
        fallback_providers=[
            "openai_compatible_chat_completion",
            "groq_chat_completion",
            "zhipu_chat_completion",
            "openrouter_chat_completion",
            "anthropic_chat_completion",
            "ollama_chat_completion",
        ],
        max_retries=3,
        retry_delay=1,
    )

    manager = ProviderManager(config=config, provider_configs=provider_configs)
    return manager
