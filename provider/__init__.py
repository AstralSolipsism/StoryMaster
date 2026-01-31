"""
Unified interface for interacting with various large language models.
"""

__version__: str = "2.0.0"

from typing import List

from .entities import (
    ProviderType,
    ProviderMeta,
    ProviderMetaData,
    TokenUsage,
    LLMResponse,
    ProviderRequest,
    RerankResult,
    ToolCallsResult,
    ChatMessage,
    ChatChoice,
    ApiResponse,
    ChatChunk,
    ModelCapabilities,
    PricingInfo,
    ServiceTier,
    ModelInfo,
    ValidationResult,
    ReasoningEffort,
    VerbosityLevel,
    AnthropicConfig,
    OpenAIConfig,
    OpenRouterConfig,
)

from .provider import (
    AbstractProvider,
    Provider,
    EmbeddingProvider,
    RerankProvider,
)

from .register import (
    provider_registry,
    provider_cls_map,
    register_provider_adapter,
    llm_tools,
)

from .manager import ProviderManager, ProviderManagerConfig
from .manager_factory import create_provider_manager
from .profile_manager import ProviderProfile, ProviderProfileManager

from . import sources
from .base import BaseModelAdapter, ApiError

__all__: List[str] = [
    "ProviderType",
    "ProviderMeta",
    "ProviderMetaData",
    "TokenUsage",
    "LLMResponse",
    "ProviderRequest",
    "RerankResult",
    "ToolCallsResult",
    "ChatMessage",
    "ChatChoice",
    "ApiResponse",
    "ChatChunk",
    "ModelCapabilities",
    "PricingInfo",
    "ServiceTier",
    "ModelInfo",
    "ValidationResult",
    "ReasoningEffort",
    "VerbosityLevel",
    "AnthropicConfig",
    "OpenAIConfig",
    "OpenRouterConfig",
    "AbstractProvider",
    "Provider",
    "EmbeddingProvider",
    "RerankProvider",
    "provider_registry",
    "provider_cls_map",
    "register_provider_adapter",
    "llm_tools",
    "ProviderManager",
    "ProviderManagerConfig",
    "create_provider_manager",
    "ProviderProfile",
    "ProviderProfileManager",
    "BaseModelAdapter",
    "ApiError",
]
