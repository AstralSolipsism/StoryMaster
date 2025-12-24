import asyncio
import aiohttp
import json
import time
import logging
import uuid
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
    ChatChoice,
)

class OllamaAdapter(BaseModelAdapter):
    """Ollama本地模型适配器"""
    
    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_CONTEXT_WINDOW = 2048
    
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
            # 使用信号量限制并发请求数量，防止资源耗尽
            semaphore = asyncio.Semaphore(10)  # 限制最多10个并发请求
            
            async def _limited_request(semaphore, model_name):
                async with semaphore:
                    return await self._request('/api/show', body={'name': model_name}, method='POST')
            
            tasks = [_limited_request(semaphore, model_data['name']) for model_data in response.get('models', [])]
            details_list = await asyncio.gather(*tasks)

            for model_data, details in zip(response.get('models', []), details_list):
                # 安全地提取和转换parameter_size为数字
                parameter_size = details.get('details', {}).get('parameter_size', self.DEFAULT_CONTEXT_WINDOW)
                context_window = self._parse_parameter_size(parameter_size)
                
                models.append(ModelInfo(
                    id=model_data.get('name'),
                    name=model_data.get('name'),
                    max_tokens=self.DEFAULT_MAX_TOKENS,
                    context_window=context_window,
                    capabilities=ModelCapabilities(
                        supports_images='clip' in str(details.get('details', {}).get('families')),
                        supports_prompt_cache=False,
                        supports_temperature=True,
                    ),
                    pricing=PricingInfo(input_price=0, output_price=0),
                    description=f"Ollama hosted model: {model_data.get('name')}",
                ))
            
            return models
        except (aiohttp.ClientError, json.JSONDecodeError, asyncio.TimeoutError) as error:
            # If Ollama service is not available, return an empty list
            logging.warning("Failed to fetch Ollama models: %s", error)
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
        # 强制启用SSL验证，不允许禁用
        # 移除禁用SSL验证的选项，提高安全性
        connector = aiohttp.TCPConnector(ssl=True)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                headers=self.default_headers,
                json=request_body
            ) as response:
                if not response.ok:
                    raise ApiError(response.status, await response.text())
                
                async for line in response.content:
                    line = line.decode('utf-8', errors='replace').strip()
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
        message = ChatMessage(
            role='assistant',
            content=response.get('message', {}).get('content', '')
        )
        choice = ChatChoice(
            index=0,
            message=message,
            finish_reason='stop' if response.get('done') else 'length'
        )
        return ApiResponse(
            id=f"ollama-{uuid.uuid4()}",
            object='chat.completion',
            created=int(time.time()),
            model=model,
            choices=[choice],
            usage=TokenUsage(
                prompt_tokens=response.get('prompt_eval_count', 0),
                completion_tokens=response.get('eval_count', 0),
                total_tokens=response.get('prompt_eval_count', 0) + response.get('eval_count', 0)
            )
        )
    
    def _transform_chunk(self, chunk: Dict[str, Any]) -> ChatChunk:
        """转换流式响应块"""
        return ChatChunk(
            id=f"ollama-chunk-{uuid.uuid4()}",
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
    
    def _parse_parameter_size(self, parameter_size) -> int:
        """
        解析parameter_size字段，将其转换为数字类型的context_window
        
        Args:
            parameter_size: 可能是数字、字符串（如'7B'、'13B'）或其他类型
            
        Returns:
            int: 转换后的context_window大小
        """
        # 如果已经是数字类型，直接返回
        if isinstance(parameter_size, (int, float)):
            return int(parameter_size)
        
        # 如果是字符串，尝试解析
        if isinstance(parameter_size, str):
            # 移除常见的后缀（如B、K、M等）
            import re
            # 匹配数字部分，可能包含小数点
            match = re.search(r'(\d+\.?\d*)', parameter_size.strip().upper())
            if match:
                number_str = match.group(1)
                try:
                    number = float(number_str)
                    # 根据后缀进行转换
                    if 'B' in parameter_size.upper():
                        # 如果是B（billion）后缀，转换为适当的大小的context window
                        # 通常参数数量与context window成正比，但不是直接映射
                        # 使用启发式规则：每B参数大约对应4K-8K context window
                        return int(number * 6000)  # 平均每B参数对应6K context window
                    elif 'M' in parameter_size.upper():
                        # M（million）后缀
                        return int(number * 6)  # 每M参数对应6 context window
                    elif 'K' in parameter_size.upper():
                        # K（thousand）后缀
                        return max(int(number / 1000 * 6000), 1024)  # 最小1024
                    else:
                        # 没有后缀，直接使用数字
                        return int(number)
                except ValueError:
                    pass
        
        # 如果无法解析，返回默认值
        return self.DEFAULT_CONTEXT_WINDOW
    
    def _should_use_reasoning_budget(self, model: ModelInfo, config: Optional[ProviderConfig] = None) -> bool:
        return False  # Ollama does not support reasoning budget