from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Any, AsyncIterable, TypedDict
from enum import Enum
from abc import ABC, abstractmethod
import time

class ReasoningEffort(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class VerbosityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass
class ModelCapabilities:
    """模型能力标志"""
    supports_images: bool = False
    supports_prompt_cache: bool = False
    supports_verbosity: Optional[bool] = None
    supports_reasoning_budget: Optional[bool] = None
    supports_temperature: Optional[bool] = None
    supports_reasoning_effort: Optional[bool] = None
    required_reasoning_budget: Optional[bool] = None

@dataclass
class PricingInfo:
    """定价信息"""
    input_price: float  # 每百万输入token价格
    output_price: float  # 每百万输出token价格
    cache_writes_price: Optional[float] = None  # 每百万缓存写入价格
    cache_reads_price: Optional[float] = None  # 每百万缓存读取价格

@dataclass
class ServiceTier:
    """服务层级定价"""
    name: Optional[str] = None  # 服务层级名称 (flex, priority等)
    context_window: int
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    cache_writes_price: Optional[float] = None
    cache_reads_price: Optional[float] = None

@dataclass
class ModelInfo:
    """模型信息"""
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

class BaseProviderConfig(TypedDict, total=False):
    """基础提供商配置"""
    api_key: Optional[str]
    base_url: Optional[str]
    timeout: Optional[int]
    max_retries: Optional[int]

class ApiModelConfig(TypedDict, total=False):
    """API模型ID配置"""
    model_id: str
    max_tokens: Optional[int]
    temperature: Optional[float]
    reasoning_effort: Optional[str]
    verbosity: Optional[str]

class ProviderConfig(BaseProviderConfig):
    """提供商特定配置"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 动态添加属性
        for key, value in kwargs.items():
            setattr(self, key, value)

class AnthropicConfig(ProviderConfig):
    """Anthropic提供商配置"""
    anthropic_base_url: Optional[str] = None
    anthropic_use_auth_token: Optional[bool] = None
    anthropic_beta_1m_context: Optional[bool] = None

class OpenAIConfig(ProviderConfig):
    """OpenAI提供商配置"""
    openai_model_id: Optional[str] = None
    openai_legacy_format: Optional[bool] = None
    openai_r1_format_enabled: Optional[bool] = None
    openai_use_azure: Optional[bool] = None
    azure_api_version: Optional[str] = None
    openai_streaming_enabled: Optional[bool] = None
    openai_headers: Optional[Dict[str, str]] = None

class OpenRouterConfig(ProviderConfig):
    """OpenRouter提供商配置"""
    openrouter_model_id: Optional[str] = None
    openrouter_specific_provider: Optional[str] = None
    openrouter_use_middle_out_transform: Optional[bool] = None

@dataclass
class TokenUsage:
    """Token使用情况"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None

@dataclass
class ChatMessage:
    """聊天消息"""
    role: str  # 'system' | 'user' | 'assistant' | 'tool'
    content: Union[str, List[Dict[str, Any]]]
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

@dataclass
class ChatChoice:
    """聊天选择"""
    index: int
    message: Optional[ChatMessage] = None
    delta: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None

@dataclass
class ApiResponse:
    """API响应"""
    id: str
    object: str
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Optional[TokenUsage] = None
    error: Optional[Exception] = None

@dataclass
class ChatChunk:
    """聊天流式响应块"""
    id: str
    object: str
    created: int
    model: str
    choices: List[ChatChoice]

@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)

class IModelAdapter(ABC):
    """模型适配器接口"""
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供商名称"""
        pass
    
    @abstractmethod
    async def get_models(self) -> List[ModelInfo]:
        """获取支持的模型列表"""
        pass
    
    @abstractmethod
    def validate_config(self, config: ProviderConfig) -> ValidationResult:
        """验证配置"""
        pass
    
    @abstractmethod
    async def chat(self, params: Dict[str, Any]) -> ApiResponse:
        """发送聊天请求"""
        pass
    
    @abstractmethod
    async def chat_stream(self, params: Dict[str, Any]) -> AsyncIterable[ChatChunk]:
        """流式聊天请求"""
        pass
    
    @abstractmethod
    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        """计算API成本"""
        pass
    
    @abstractmethod
    def get_max_output_tokens(self, model: str, config: Optional[ProviderConfig] = None) -> int:
        """获取最大输出token数"""
        pass