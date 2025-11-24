import aiohttp
import json
import os
import logging
from typing import AsyncIterable, Dict, Any, List, Optional

from ..base import BaseModelAdapter, ApiError
from ..interfaces import (
    ModelInfo,
    ProviderConfig,
    ModelCapabilities,
    PricingInfo,
    ApiResponse,
    ChatChunk,
    TokenUsage,
    ChatChoice,
    ChatMessage,
)

class OpenRouterAdapter(BaseModelAdapter):
    """OpenRouter动态模型适配器"""
    
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MAX_TOKENS = 4096
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
    
    @property
    def provider_name(self) -> str:
        return "openrouter"
    
    def _get_default_base_url(self) -> str:
        return self.config.get('openrouter_base_url', self.DEFAULT_BASE_URL)
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = {
            'Content-Type': 'application/json',
            # 使用环境变量或配置文件中的值，避免硬编码
            'HTTP-Referer': self.config.get('http_referer',
                os.environ.get('HTTP_REFERER', 'https://example.com')),
            # 使用环境变量或配置文件中的值，避免硬编码
            'X-Title': self.config.get('x_title',
                os.environ.get('APP_NAME', 'StoryMaster')),
        }
        
        api_key = self.config.get('api_key') # Standardized to 'api_key'
        if api_key:
            headers['Authorization'] = f"Bearer {api_key}"
        
        return headers
    
    async def _fetch_models(self) -> List[ModelInfo]:
        """获取OpenRouter模型列表"""
        try:
            response = await self._request('/models', method='GET')
        except ApiError as e:
            self.logger.error(f"Failed to fetch OpenRouter models: {e.message}")
            return []

        models = []
        for model_data in response.get('data', []):
            if not model_data.get('id') or not model_data.get('context_length'):
                continue
            
            pricing = model_data.get('pricing', {})
            capabilities_data = model_data.get('architecture', {})
            models.append(ModelInfo(
                id=model_data.get('id'),
                name=model_data.get('name', model_data.get('id')),
                max_tokens=model_data.get('top_provider', {}).get('max_completion_tokens') or self.DEFAULT_MAX_TOKENS,
                context_window=model_data.get('context_length'),
                capabilities=ModelCapabilities(
                    supports_images='vision' in capabilities_data.get('modality', ''),
                    supports_prompt_cache=capabilities_data.get('prompt_caching', False),
                    supports_reasoning_budget=capabilities_data.get('reasoning_budget', False),
                ),
                pricing=PricingInfo(
                    input_price=float(pricing.get('prompt', 0)) * 1_000_000,
                    output_price=float(pricing.get('completion', 0)) * 1_000_000,
                    cache_writes_price=float(pricing.get('cache_write', {}).get('prompt', 0)) * 1_000_000,
                    cache_reads_price=float(pricing.get('cache_read', {}).get('prompt', 0)) * 1_000_000,
                ),
                description=model_data.get('description'),
            ))
        
        return models
    
    async def chat(self, params: Dict[str, Any]) -> ApiResponse:
        """发送聊天请求"""
        request_body = self._build_chat_request(params)
        
        response = await self._request('/chat/completions', body=request_body, method='POST')
        return self._transform_response(response)
    
    async def chat_stream(self, params: Dict[str, Any]) -> AsyncIterable[ChatChunk]:
        """流式聊天请求"""
        request_body = {**self._build_chat_request(params), 'stream': True}
        
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/chat/completions",
            headers=self.default_headers,
            json=request_body
        ) as response:
            if not response.ok:
                raise ApiError(response.status, await response.text())
            
            json_decode_errors = 0
            unicode_decode_errors = 0
            
            async for line in response.content:
                try:
                    line = line.decode('utf-8').strip()
                except UnicodeDecodeError as e:
                    unicode_decode_errors += 1
                    self.logger.warning(f"Unicode decode error in stream: {e}")
                    continue
                    
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        return
                    
                    try:
                        parsed = json.loads(data)
                        yield self._transform_chunk(parsed)
                    except json.JSONDecodeError as e:
                        json_decode_errors += 1
                        self.logger.warning(f"JSON decode error in stream: {e}, data: {data[:100]}...")
                        continue
            
            # 记录错误统计
            if json_decode_errors > 0:
                self.logger.error(f"Total JSON decode errors: {json_decode_errors}")
            if unicode_decode_errors > 0:
                self.logger.error(f"Total Unicode decode errors: {unicode_decode_errors}")
    
    def _build_chat_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """构建聊天请求"""
        request = {
            'model': params.get('model'),
            'messages': params.get('messages'),
            'max_tokens': params.get('max_tokens') or self.get_max_output_tokens(params.get('model'), self.config),
        }
        
        if 'temperature' in params:
            request['temperature'] = params['temperature']
        if 'tools' in params:
            request['tools'] = params['tools']
        if 'tool_choice' in params:
            request['tool_choice'] = params['tool_choice']
        
        specific_provider = self.config.get('openrouter_specific_provider')
        use_middle_out_transform = self.config.get('openrouter_use_middle_out_transform', True)

        if specific_provider:
            request['provider'] = {
                'order': [specific_provider],
                'allow_fallbacks': False,
            }
        
        if use_middle_out_transform:
            request['transforms'] = ['middle-out']
        
        return request
    
    def _transform_response(self, response: Dict[str, Any]) -> ApiResponse:
        """转换响应格式"""
        usage_data = response.get('usage')
        return ApiResponse(
            id=response.get('id'),
            object='chat.completion',
            created=response.get('created'),
            model=response.get('model'),
            choices=[
                ChatChoice(
                    index=choice.get('index'),
                    message=ChatMessage(**choice.get('message')),
                    finish_reason=choice.get('finish_reason')
                ) for choice in response.get('choices', [])
            ],
            usage=TokenUsage(**usage_data) if usage_data else None
        )
    
    def _transform_chunk(self, chunk: Dict[str, Any]) -> ChatChunk:
        """转换流式响应块"""
        return ChatChunk(
            id=chunk.get('id'),
            object='chat.completion.chunk',
            created=chunk.get('created'),
            model=chunk.get('model'),
            choices=chunk.get('choices', [])
        )
    
    
    def _requires_api_key(self) -> bool:
        return True
    
    def _is_anthropic_style(self) -> bool:
        return False
    
    def _should_use_reasoning_budget(self, model: ModelInfo, config: Optional[ProviderConfig] = None) -> bool:
        if not model.capabilities.supports_reasoning_budget:
            return False
        
        enable_effort = config and config.get('enable_reasoning_effort')
        return bool(model.capabilities.required_reasoning_budget or enable_effort)