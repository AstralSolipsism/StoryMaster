import aiohttp
import json
import asyncio
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from abc import ABC, abstractmethod

from .interfaces import (
    IModelAdapter,
    ModelInfo,
    ProviderConfig,
    ValidationResult,
    TokenUsage,
)

class ApiError(Exception):
    """API错误"""
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"API Error {status}: {message}")

class BaseHttpClient(ABC):
    """HTTP客户端抽象类"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.base_url = config.get('base_url') or self._get_default_base_url()
        self.default_headers = self._get_default_headers()
        self._session: Optional[aiohttp.ClientSession] = None
    
    @abstractmethod
    def _get_default_base_url(self) -> str:
        """获取默认基础URL"""
        pass
    
    @abstractmethod
    def _get_default_headers(self) -> Dict[str, str]:
        """获取默认请求头"""
        pass
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 aiohttp.ClientSession"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self.config.get('timeout', 30),
                connect=10
            )
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _request(self, endpoint: str, **kwargs) -> Any:
        """发送HTTP请求"""
        url = f"{self.base_url}{endpoint}"
        request_options = self._create_request_options(
            kwargs.get('body'),
            kwargs.get('headers')
        )
        
        session = await self._get_session()
        
        try:
            async with session.request(
                method=kwargs.get('method', 'POST'),
                url=url,
                headers=request_options['headers'],
                json=request_options['body'],
                timeout=request_options['timeout']
            ) as response:
                if not response.ok:
                    error_text = await response.text()
                    raise ApiError(response.status, error_text)
                
                return await response.json()
        except asyncio.TimeoutError:
            raise ApiError(408, "Request timeout")
    
    def _create_request_options(self, body: Any, custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """创建请求选项"""
        return {
            'headers': {**self.default_headers, **(custom_headers or {})},
            'body': body,
            'timeout': self.config.get('timeout', 30),
        }

class BaseModelAdapter(BaseHttpClient, IModelAdapter):
    """基础模型适配器抽象类"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.models: Dict[str, ModelInfo] = {}
    
    async def get_models(self) -> List[ModelInfo]:
        """获取支持的模型列表"""
        if not self.models:
            models = await self._fetch_models()
            self.models = {model.id: model for model in models}
        return list(self.models.values())
    
    def _get_model(self, model_id: str) -> Optional[ModelInfo]:
        """获取模型信息"""
        return self.models.get(model_id)
    
    def validate_config(self, config: ProviderConfig) -> ValidationResult:
        """验证配置"""
        errors = []
        
        if not config.get('api_key') and self._requires_api_key():
            errors.append('需要API密钥')
        
        base_url = config.get('base_url')
        if base_url and not self._is_valid_url(base_url):
            errors.append('无效的基础URL')
        
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
    
    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        """计算API成本"""
        model_info = self._get_model(model)
        if not model_info:
            return 0.0
        
        if not model_info.pricing or not usage:
            return 0.0
        
        pricing = model_info.pricing
        input_cost = (usage.prompt_tokens / 1_000_000) * pricing.input_price
        output_cost = (usage.completion_tokens / 1_000_000) * pricing.output_price
        
        cache_cost = 0.0
        if usage.cache_creation_input_tokens and pricing.cache_writes_price:
            cache_cost += (usage.cache_creation_input_tokens / 1_000_000) * pricing.cache_writes_price
        if usage.cache_read_input_tokens and pricing.cache_reads_price:
            cache_cost += (usage.cache_read_input_tokens / 1_000_000) * pricing.cache_reads_price
        
        return input_cost + output_cost + cache_cost
    
    def get_max_output_tokens(self, model: str, config: Optional[ProviderConfig] = None) -> int:
        """获取最大输出token数"""
        model_info = self._get_model(model)
        if not model_info:
            return 4096
        
        # 检查是否使用推理预算
        if self._should_use_reasoning_budget(model_info, config):
            return config.get('model_max_tokens', 16384) if config else 16384
        
        # 检查是否为Anthropic风格的混合推理模型
        if (model_info.capabilities.supports_reasoning_budget and 
            self._is_anthropic_style()):
            return 8192
        
        return model_info.max_tokens
    
    # 抽象方法，子类必须实现
    @abstractmethod
    async def _fetch_models(self) -> List[ModelInfo]:
        """获取模型列表"""
        pass
    
    @abstractmethod
    def _requires_api_key(self) -> bool:
        """是否需要API密钥"""
        pass
    
    def _is_valid_url(self, url: str) -> bool:
        """验证URL有效性"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except (ValueError, TypeError):
            return False
    
    @abstractmethod
    def _is_anthropic_style(self) -> bool:
        """是否为Anthropic风格API"""
        pass
    
    @abstractmethod
    def _should_use_reasoning_budget(self, model: ModelInfo, config: Optional[ProviderConfig] = None) -> bool:
        """是否应该使用推理预算"""
        pass