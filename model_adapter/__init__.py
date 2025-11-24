"""
A unified interface for interacting with various large language models.

This package provides a standardized way to:
- List available models from different providers.
- Send chat completion requests (blocking and streaming).
- Calculate the cost of API usage.
- Validate provider configurations.

It includes a scheduler to automatically select the best model based on cost,
latency, and other factors.
"""

__version__: str = "1.0.0"

# Interfaces
from .interfaces import (
    ModelInfo,
    ProviderConfig,
    ChatMessage,
    ApiResponse,
    ChatChunk,
    TokenUsage,
    IModelAdapter,
    ReasoningEffort,
    VerbosityLevel,
    ModelCapabilities,
    PricingInfo,
    ServiceTier,
    ValidationResult,
    AnthropicConfig,
    OpenAIConfig,
    OpenRouterConfig,
)

# Base classes
from .base import BaseModelAdapter, ApiError

# Factory
from .factory import ModelAdapterFactory

# Scheduler
from .scheduler import ModelScheduler, SchedulerConfig, RequestContext

# 按功能分组组织__all__列表，提高可维护性
_interfaces = [
    "ModelInfo", "ProviderConfig", "ChatMessage", "ApiResponse", "ChatChunk",
    "TokenUsage", "IModelAdapter", "ReasoningEffort", "VerbosityLevel",
    "ModelCapabilities", "PricingInfo", "ServiceTier", "ValidationResult",
    "AnthropicConfig", "OpenAIConfig", "OpenRouterConfig"
]

_base_classes = [
    "BaseModelAdapter", "ApiError"
]

_factory_scheduler = [
    "ModelAdapterFactory", "ModelScheduler", "SchedulerConfig", "RequestContext"
]

__all__ = _interfaces + _base_classes + _factory_scheduler