from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict, Union


class ReasoningEffort(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerbosityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProviderType(Enum):
    CHAT_COMPLETION = "chat_completion"
    EMBEDDING = "embedding"
    RERANK = "rerank"


@dataclass
class ProviderMeta:
    """Basic runtime metadata for a provider instance."""

    id: str
    model: Optional[str]
    type: str
    provider_type: ProviderType = ProviderType.CHAT_COMPLETION


@dataclass
class ProviderMetaData(ProviderMeta):
    """Registration metadata for a provider adapter."""

    desc: str = ""
    cls_type: Any = None
    default_config_tmpl: Optional[dict] = None
    provider_display_name: Optional[str] = None


@dataclass
class ToolCallsResult:
    tool_calls_info: Dict[str, Any]
    tool_calls_result: List[Dict[str, Any]]

    def to_openai_messages(self) -> List[Dict[str, Any]]:
        return [self.tool_calls_info, *self.tool_calls_result]


class BaseProviderConfig(TypedDict, total=False):
    api_key: Optional[str]
    base_url: Optional[str]
    timeout: Optional[int]
    max_retries: Optional[int]


class ProviderConfig(BaseProviderConfig, total=False):
    pass


class AnthropicConfig(ProviderConfig):
    anthropic_base_url: Optional[str] = None
    anthropic_use_auth_token: Optional[bool] = None
    anthropic_beta_1m_context: Optional[bool] = None


class OpenAIConfig(ProviderConfig):
    openai_model_id: Optional[str] = None
    openai_legacy_format: Optional[bool] = None
    openai_r1_format_enabled: Optional[bool] = None
    openai_use_azure: Optional[bool] = None
    azure_api_version: Optional[str] = None
    openai_streaming_enabled: Optional[bool] = None
    openai_headers: Optional[Dict[str, str]] = None


class OpenRouterConfig(ProviderConfig):
    openrouter_model_id: Optional[str] = None
    openrouter_specific_provider: Optional[str] = None
    openrouter_use_middle_out_transform: Optional[bool] = None


@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None


@dataclass
class ChatMessage:
    role: str
    content: Union[str, List[Dict[str, Any]]]
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ChatChoice:
    index: int
    message: Optional[ChatMessage] = None
    delta: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None


@dataclass
class ApiResponse:
    id: str
    object: str
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Optional[TokenUsage] = None
    error: Optional[str] = None


@dataclass
class ChatChunk:
    id: str
    object: str
    created: int
    model: str
    choices: List[Dict[str, Any]]


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class ProviderRequest:
    messages: List[ChatMessage]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    priority: str = "medium"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tools: Optional[List[Any]] = None
    tool_choice: Optional[Any] = None
    system: Optional[str] = None
    reasoning_budget: Optional[int] = None


@dataclass
class ModelCapabilities:
    supports_images: bool = False
    supports_prompt_cache: bool = False
    supports_verbosity: Optional[bool] = None
    supports_reasoning_budget: Optional[bool] = None
    supports_temperature: Optional[bool] = None
    supports_reasoning_effort: Optional[bool] = None
    required_reasoning_budget: Optional[bool] = None


@dataclass
class PricingInfo:
    input_price: float
    output_price: float
    cache_writes_price: Optional[float] = None
    cache_reads_price: Optional[float] = None


@dataclass
class ServiceTier:
    context_window: int
    name: Optional[str] = None
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    cache_writes_price: Optional[float] = None
    cache_reads_price: Optional[float] = None


@dataclass
class ModelInfo:
    id: str
    name: str
    max_tokens: int
    context_window: int
    capabilities: ModelCapabilities
    pricing: PricingInfo
    max_thinking_tokens: Optional[int] = None
    tiers: Optional[List[ServiceTier]] = None
    description: Optional[str] = None
    reasoning_effort: Optional[ReasoningEffort] = None
    supported_parameters: Optional[List[str]] = None
    deprecated: bool = False
    cachable_fields: Optional[List[str]] = None
    min_tokens_per_cache_point: Optional[int] = None
    max_cache_points: Optional[int] = None


@dataclass
class RerankResult:
    index: int
    relevance_score: float


@dataclass
class LLMResponse:
    role: str
    result_text: str = ""
    tools_call_args: List[Dict[str, Any]] = field(default_factory=list)
    tools_call_name: List[str] = field(default_factory=list)
    tools_call_ids: List[str] = field(default_factory=list)
    tools_call_extra_content: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reasoning_content: str = ""
    is_chunk: bool = False
    id: Optional[str] = None
    usage: Optional[TokenUsage] = None
