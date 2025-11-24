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

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        # 使用字典存储每个请求的usage信息，避免并发冲突
        self._stream_usage_map: Dict[str, Dict[str, Any]] = {}
    
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
            if not self._validate_api_key(api_key):
                raise ValueError("Invalid Anthropic API key format.")
            headers['x-api-key'] = api_key
        
        if self.config.get('anthropic_beta_1m_context'):
            headers['anthropic-beta'] = 'context-1m-2025-08-07'
        
        return headers
    
    async def _fetch_models(self) -> List[ModelInfo]:
        """从JSON文件加载Anthropic模型列表"""
        models_file = self.config.get('anthropic_models_file', 'model_adapter/adapters/anthropic_models.json')
        try:
            with open(models_file, 'r', encoding='utf-8') as f:
                models_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

        models = []
        models_data = models_config.get('models', [])
        for model_data in models_data:
            # 从第一个tier获取pricing信息，或者使用默认值
            tiers = model_data.get('tiers', [])
            if tiers:
                pricing_data = tiers[0]  # 使用第一个tier的pricing信息
                pricing = PricingInfo(
                    input_price=pricing_data.get('input_price', 0),
                    output_price=pricing_data.get('output_price', 0),
                    cache_writes_price=pricing_data.get('cache_writes_price', 0),
                    cache_reads_price=pricing_data.get('cache_reads_price', 0)
                )
                context_window = pricing_data.get('context_window', 200000)
            else:
                # 默认pricing信息
                pricing = PricingInfo(
                    input_price=0,
                    output_price=0,
                    cache_writes_price=0,
                    cache_reads_price=0
                )
                context_window = 200000
            
            models.append(ModelInfo(
                id=model_data['id'],
                name=model_data['name'],
                max_tokens=model_data['max_tokens'],
                context_window=context_window,
                capabilities=ModelCapabilities(**model_data['capabilities']),
                pricing=pricing,
                tiers=[ServiceTier(**tier) for tier in tiers]
            ))
        return models
    
    async def chat(self, params: Dict[str, Any]) -> ApiResponse:
        """发送聊天请求"""
        request_body = self._build_chat_request(params)
        
        response = await self._request('/v1/messages', body=request_body, method='POST')
        return self._transform_response(response, params.get('model'))
    
    async def chat_stream(self, params: Dict[str, Any]) -> AsyncIterable[ChatChunk]:
        """流式聊天请求"""
        request_body = {**self._build_chat_request(params), 'stream': True}
        
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/v1/messages",
            headers=self.default_headers,
            json=request_body
        ) as response:
                if not response.ok:
                    raise ApiError(response.status, await response.text())
                
                buffer = b""
                max_buffer_size = 10 * 1024 * 1024  # 10MB缓冲区限制
                
                async for chunk in response.content.iter_any():
                    buffer += chunk
                    
                    # 检查缓冲区大小，防止内存溢出
                    if len(buffer) > max_buffer_size:
                        raise RuntimeError(f"流式响应缓冲区过大: {len(buffer)} bytes")
                    
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
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
                        try:
                            # Expected format: "data:image/jpeg;base64,..."
                            header, base64_data = image_data.split(',', 1)
                            if 'base64' not in header:
                                continue
                            media_type = header.split(';')[0].split(':')[1]
                            content_list.append({
                                'type': 'image',
                                'source': {
                                    'type': 'base64',
                                    'media_type': media_type,
                                    'data': base64_data,
                                },
                            })
                        except (ValueError, IndexError):
                            # Skip malformed image data
                            continue
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
        chunk_id = chunk.get('id', f"anthropic-chunk-{int(time.time())}")
        
        if chunk_type == 'message_start':
            # 为每个请求存储独立的usage信息
            self._stream_usage_map[chunk_id] = chunk.get('message', {}).get('usage', {})
            return None # Don't yield start event
        
        if chunk_type == 'message_delta':
            finish_reason = chunk.get('delta', {}).get('stop_reason')
        elif chunk_type == 'message_stop':
            finish_reason = chunk.get('stop_reason')
            # 清理该请求的usage信息
            if chunk_id in self._stream_usage_map:
                del self._stream_usage_map[chunk_id]
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
            id=chunk_id,
            object='chat.completion.chunk',
            created=int(time.time()),
            model=model,
            choices=[{
                'index': chunk.get('index', 0),
                'delta': delta,
                'finish_reason': finish_reason
            }]
        )
    
    def get_stream_usage(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """获取特定请求的usage信息"""
        return self._stream_usage_map.get(chunk_id)
    
    def clear_stream_usage(self, chunk_id: str = None) -> None:
        """清理usage信息"""
        if chunk_id:
            self._stream_usage_map.pop(chunk_id, None)
        else:
            self._stream_usage_map.clear()
    
    def _requires_api_key(self) -> bool:
        return True
    
    def _is_anthropic_style(self) -> bool:
        return True
    
    def _should_use_reasoning_budget(self, model: ModelInfo, config: Optional[ProviderConfig] = None) -> bool:
        if not model.capabilities.supports_reasoning_budget:
            return False
        
        enable_effort = config and config.get('enable_reasoning_effort')
        return bool(model.capabilities.required_reasoning_budget or enable_effort)
    
    def _validate_api_key(self, api_key: str) -> bool:
        """验证Anthropic API密钥格式"""
        import re
        import os
        
        # 检查类型
        if not isinstance(api_key, str):
            return False
        
        # 检查是否为测试环境
        is_test_env = os.environ.get('TESTING', 'false').lower() == 'true'
        
        if is_test_env:
            # 测试环境下允许较宽松的验证
            if len(api_key) < 10:
                return False
            test_pattern = r'^sk-ant-[a-zA-Z0-9_-]+$'
            return bool(re.match(test_pattern, api_key))
        else:
            # 生产环境下使用严格的验证
            if len(api_key) < 20:  # 生产环境要求更长的密钥
                return False
            
            # 使用正则表达式验证完整格式
            # Anthropic API密钥格式: sk-ant-api03-...
            pattern = r'^sk-ant-api03-[a-zA-Z0-9_-]{95,}$'
            if not re.match(pattern, api_key):
                # 也支持旧格式 sk-...
                old_pattern = r'^sk-[a-zA-Z0-9_-]{20,}$'
                return bool(re.match(old_pattern, api_key))
            
            return True
