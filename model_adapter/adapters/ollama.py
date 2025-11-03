import aiohttp
import json
import time
from typing import AsyncIterable, Dict, Any, List, Optional

from ..base import BaseModelAdapter, ApiError
from ..interfaces import (
    ModelInfo,
    ProviderConfig,
    ModelCapabilities,
    PricingInfo,
    ApiResponse,
    ChatChunk,
    ChatMessage,
    TokenUsage,
)

class OllamaAdapter(BaseModelAdapter):
    """Ollama本地模型适配器"""
    
    DEFAULT_BASE_URL = "http://localhost:11434"
    
    @property
    def provider_name(self) -> str:
        return "ollama"
    
    def _get_default_base_url(self) -> str:
        return self.config.get('ollama_base_url', self.DEFAULT_BASE_URL)
    
    def _get_default_headers(self) -> Dict[str, str]:
        return {'Content-Type': 'application/json'}
    
    async def _fetch_models(self) -> List[ModelInfo]:
        """获取Ollama模型列表"""
        try:
            response = await self._request('/api/tags', method='GET')
            
            models = []
            for model_data in response.get('models', []):
                # Fetch detailed info for each model
                details = await self._request('/api/show', body={'name': model_data['name']}, method='POST')
                
                models.append(ModelInfo(
                    id=model_data.get('name'),
                    name=model_data.get('name'),
                    max_tokens=4096,  # Default, can be overridden by model params
                    context_window=details.get('details', {}).get('parameter_size', 2048),
                    capabilities=ModelCapabilities(
                        supports_images='clip' in str(details.get('details', {}).get('families')),
                        supports_prompt_cache=False,
                        supports_temperature=True,
                    ),
                    pricing=PricingInfo(input_price=0, output_price=0),
                    description=f"Ollama hosted model: {model_data.get('name')}",
                ))
            
            return models
        except Exception as error:
            # If Ollama service is not available, return an empty list
            print(f"Failed to fetch Ollama models: {error}")
            return []
    
    async def chat(self, params: Dict[str, Any]) -> ApiResponse:
        """发送聊天请求"""
        request_body = self._build_chat_request(params)
        
        response = await self._request('/api/chat', body=request_body, method='POST')
        return self._transform_response(response, params.get('model'))
    
    async def chat_stream(self, params: Dict[str, Any]) -> AsyncIterable[ChatChunk]:
        """流式聊天请求"""
        request_body = {**self._build_chat_request(params), 'stream': True}
        
        timeout = aiohttp.ClientTimeout(total=self.config.get('timeout', 60))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                headers=self.default_headers,
                json=request_body
            ) as response:
                if not response.ok:
                    raise ApiError(response.status, await response.text())
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line:
                        try:
                            parsed = json.loads(line)
                            yield self._transform_chunk(parsed)
                        except json.JSONDecodeError:
                            continue
    
    def _build_chat_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """构建聊天请求"""
        request = {
            'model': params.get('model'),
            'messages': params.get('messages'),
            'options': {
                'temperature': params.get('temperature'),
                'num_predict': params.get('max_tokens') or self.get_max_output_tokens(params.get('model'), self.config),
            },
        }
        
        num_ctx = self.config.get('ollama_num_ctx')
        if num_ctx:
            request['options']['num_ctx'] = num_ctx
        
        return request
    
    def _transform_response(self, response: Dict[str, Any], model: str) -> ApiResponse:
        """转换响应格式"""
        return ApiResponse(
            id=f"ollama-{int(time.time())}",
            object='chat.completion',
            created=int(time.time()),
            model=model,
            choices=[{
                'index': 0,
                'message': ChatMessage(
                    role='assistant',
                    content=response.get('message', {}).get('content', '')
                ),
                'finish_reason': 'stop' if response.get('done') else 'length'
            }],
            usage=TokenUsage(
                prompt_tokens=response.get('prompt_eval_count', 0),
                completion_tokens=response.get('eval_count', 0),
                total_tokens=response.get('prompt_eval_count', 0) + response.get('eval_count', 0)
            )
        )
    
    def _transform_chunk(self, chunk: Dict[str, Any]) -> ChatChunk:
        """转换流式响应块"""
        return ChatChunk(
            id=f"ollama-chunk-{int(time.time())}",
            object='chat.completion.chunk',
            created=int(time.time()),
            model=chunk.get('model'),
            choices=[{
                'index': 0,
                'delta': {
                    'content': chunk.get('message', {}).get('content', '')
                },
                'finish_reason': 'stop' if chunk.get('done') else None
            }]
        )
    
    def _requires_api_key(self) -> bool:
        return False
    
    def _is_anthropic_style(self) -> bool:
        return False
    
    def _should_use_reasoning_budget(self, model: ModelInfo, config: Optional[ProviderConfig] = None) -> bool:
        return False  # Ollama does not support reasoning budget