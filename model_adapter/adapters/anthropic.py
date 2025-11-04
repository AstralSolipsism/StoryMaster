import asyncio
import json
import time
from typing import AsyncIterable, Dict, Any, List, Optional
from urllib.parse import urlparse
import aiohttp

from ..base import BaseModelAdapter, ApiError
from ..interfaces import (
    ModelInfo,
    ProviderConfig,
    ModelCapabilities,
    PricingInfo,
    ServiceTier,
    ApiResponse,
    ChatChunk,
    ChatMessage,
    TokenUsage,
    ChatChoice,
)

class AnthropicAdapter(BaseModelAdapter):
    """Anthropic模型适配器"""
    
    DEFAULT_BASE_URL = "https://api.anthropic.com"
    DEFAULT_MAX_TOKENS = 8192
    
    @property
    def provider_name(self) -> str:
        return "anthropic"
    
    def _get_default_base_url(self) -> str:
        return self.config.get('anthropic_base_url', self.DEFAULT_BASE_URL)
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = {
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01'
        }
        
        api_key = self.config.get('api_key')
        if api_key:
            headers['x-api-key'] = api_key
        
        if self.config.get('anthropic_beta_1m_context'):
            headers['anthropic-beta'] = 'context-1m-2025-08-07'
        
        return headers
    
    async def _fetch_models(self) -> List[ModelInfo]:
        """Anthropic模型列表是静态的"""
        # This is a static list based on the documentation.
        # In a real-world scenario, this might be fetched from a configuration service
        # or a less frequently updated API endpoint.
        return [
            ModelInfo(
                id="claude-3-5-sonnet-20240620",
                name="Claude 3.5 Sonnet",
                max_tokens=8192,
                context_window=200000,
                capabilities=ModelCapabilities(
                    supports_images=True,
                    supports_prompt_cache=True,
                    supports_reasoning_budget=True,
                ),
                pricing=PricingInfo(
                    input_price=3.0,
                    output_price=15.0,
                    cache_writes_price=3.75,
                    cache_reads_price=0.3,
                ),
                tiers=[
                    ServiceTier(
                        name="default",
                        context_window=200000,
                        input_price=3.0,
                        output_price=15.0,
                        cache_writes_price=3.75,
                        cache_reads_price=0.3,
                    ),
                    ServiceTier(
                        name="1m-context",
                        context_window=1000000,
                        input_price=6.0,
                        output_price=22.5,
                        cache_writes_price=7.5,
                        cache_reads_price=0.6,
                    ),
                ],
            ),
            # Adding other models for completeness
            ModelInfo(
                id="claude-3-opus-20240229",
                name="Claude 3 Opus",
                max_tokens=4096,
                context_window=200000,
                capabilities=ModelCapabilities(supports_images=True),
                pricing=PricingInfo(input_price=15.0, output_price=75.0),
            ),
            ModelInfo(
                id="claude-3-sonnet-20240229",
                name="Claude 3 Sonnet",
                max_tokens=4096,
                context_window=200000,
                capabilities=ModelCapabilities(supports_images=True),
                pricing=PricingInfo(input_price=3.0, output_price=15.0),
            ),
            ModelInfo(
                id="claude-3-haiku-20240307",
                name="Claude 3 Haiku",
                max_tokens=4096,
                context_window=200000,
                capabilities=ModelCapabilities(supports_images=True),
                pricing=PricingInfo(input_price=0.25, output_price=1.25),
            ),
        ]
    
    async def chat(self, params: Dict[str, Any]) -> ApiResponse:
        """发送聊天请求"""
        request_body = self._build_chat_request(params)
        
        response = await self._request('/v1/messages', body=request_body, method='POST')
        return self._transform_response(response, params.get('model'))
    
    async def chat_stream(self, params: Dict[str, Any]) -> AsyncIterable[ChatChunk]:
        """流式聊天请求"""
        request_body = {**self._build_chat_request(params), 'stream': True}
        
        timeout = aiohttp.ClientTimeout(total=self.config.get('timeout', 30))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{self.base_url}/v1/messages",
                headers=self.default_headers,
                json=request_body
            ) as response:
                if not response.ok:
                    raise ApiError(response.status, await response.text())
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]':
                            return
                        
                        try:
                            parsed = json.loads(data)
                            transformed_chunk = self._transform_chunk(parsed, params.get('model'))
                            if transformed_chunk:
                                yield transformed_chunk
                        except json.JSONDecodeError:
                            continue
    
    def _build_chat_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """构建聊天请求"""
        model_id = params.get('model')
        request = {
            'model': model_id,
            'max_tokens': params.get('max_tokens') or self.get_max_output_tokens(
                model_id, 
                self.config
            ),
            'messages': self._transform_messages(params.get('messages', [])),
        }
        
        if 'temperature' in params:
            request['temperature'] = params['temperature']
        
        if 'tools' in params:
            request['tools'] = params['tools']

        if 'tool_choice' in params:
            request['tool_choice'] = params['tool_choice']

        if 'system' in params:
            request['system'] = params['system']
        
        reasoning_budget = params.get('reasoning_budget')
        model_info = self._get_model(model_id)
        if (reasoning_budget and model_info and
            self._should_use_reasoning_budget(model_info, self.config)):
            request['reasoning_budget'] = reasoning_budget
        
        return request
    
    def _transform_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换消息格式"""
        transformed = []
        for msg_data in messages:
            msg = ChatMessage(**msg_data) if isinstance(msg_data, dict) else msg_data
            
            # Handle tool calls
            if msg.role == 'tool':
                transformed.append({
                    'role': 'user',
                    'content': [
                        {
                            'type': 'tool_result',
                            'tool_use_id': msg.tool_call_id,
                            'content': msg.content
                        }
                    ]
                })
                continue

            if isinstance(msg.content, str):
                content_list = [{'type': 'text', 'text': msg.content}]
            else: # It's a list of content blocks
                content_list = []
                for item in msg.content:
                    if item.get('type') == 'image_url':
                        # Assuming image_url is a dict with 'url' key like "data:image/jpeg;base64,..."
                        image_data = item['image_url']['url']
                        media_type = image_data.split(';')[0].split(':')[1]
                        base64_data = image_data.split(',')[1]
                        content_list.append({
                            'type': 'image',
                            'source': {
                                'type': 'base64',
                                'media_type': media_type,
                                'data': base64_data,
                            },
                        })
                    else: # text block
                        content_list.append(item)
            
            transformed_message = {'role': msg.role, 'content': content_list}
            if msg.tool_calls:
                 transformed_message['tool_calls'] = msg.tool_calls
            
            transformed.append(transformed_message)

        return transformed
    
    def _transform_response(self, response: Dict[str, Any], model: str) -> ApiResponse:
        """转换响应格式"""
        usage_data = response.get('usage', {})
        content_blocks = response.get('content', [])
        
        # Extract text and tool calls from content blocks
        text_content = ""
        tool_calls = []
        for block in content_blocks:
            if block.get('type') == 'text':
                text_content += block.get('text', '')
            elif block.get('type') == 'tool_use':
                tool_calls.append({
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        message = ChatMessage(
            role='assistant',
            content=text_content,
            tool_calls=tool_calls if tool_calls else None
        )

        return ApiResponse(
            id=response.get('id'),
            object='chat.completion',
            created=int(time.time()),
            model=model,
            choices=[
                ChatChoice(
                    index=0,
                    message=message,
                    finish_reason=response.get('stop_reason')
                )
            ],
            usage=TokenUsage(
                prompt_tokens=usage_data.get('input_tokens', 0),
                completion_tokens=usage_data.get('output_tokens', 0),
                total_tokens=(
                    usage_data.get('input_tokens', 0) +
                    usage_data.get('output_tokens', 0)
                ),
                cache_creation_input_tokens=usage_data.get('cache_creation_input_tokens'),
                cache_read_input_tokens=usage_data.get('cache_read_input_tokens'),
            )
        )
    
    def _transform_chunk(self, chunk: Dict[str, Any], model: str) -> Optional[ChatChunk]:
        """转换流式响应块"""
        chunk_type = chunk.get('type')
        if chunk_type == 'message_start':
            self.stream_usage = chunk.get('message', {}).get('usage', {})
            return None # Don't yield start event
        
        if chunk_type == 'message_delta':
            finish_reason = chunk.get('delta', {}).get('stop_reason')
        elif chunk_type == 'message_stop':
            finish_reason = chunk.get('stop_reason')
        else:
            finish_reason = None

        delta = {}
        if chunk_type == 'content_block_delta':
            delta_content = chunk.get('delta', {})
            if delta_content.get('type') == 'text_delta':
                delta = {'content': delta_content.get('text', '')}
            elif delta_content.get('type') == 'tool_use_delta':
                 # This part needs to be adapted based on how tool use streaming is handled
                 pass

        if not delta and not finish_reason:
            return None

        return ChatChunk(
            id=chunk.get('id', f"anthropic-chunk-{int(time.time())}"),
            object='chat.completion.chunk',
            created=int(time.time()),
            model=model,
            choices=[{
                'index': chunk.get('index', 0),
                'delta': delta,
                'finish_reason': finish_reason
            }]
        )
    
    def _requires_api_key(self) -> bool:
        return True
    
    def _is_anthropic_style(self) -> bool:
        return True
    
    def _should_use_reasoning_budget(self, model: ModelInfo, config: Optional[ProviderConfig] = None) -> bool:
        if not model.capabilities.supports_reasoning_budget:
            return False
        
        enable_effort = config and config.get('enable_reasoning_effort')
        return bool(model.capabilities.required_reasoning_budget or enable_effort)
