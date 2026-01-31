import asyncio
import json
import os
import time
from typing import AsyncIterable, Dict, Any, List, Optional

import aiohttp

from ..base import BaseModelAdapter, ApiError
from ..entities import (
    ApiResponse,
    ChatChunk,
    ChatChoice,
    ChatMessage,
    ModelCapabilities,
    ModelInfo,
    PricingInfo,
    ProviderConfig,
    ServiceTier,
    TokenUsage,
)
from ..register import register_provider_adapter


@register_provider_adapter(
    "anthropic_chat_completion",
    desc="Anthropic chat completion provider",
)
class ProviderAnthropic(BaseModelAdapter):
    """Anthropic provider adapter."""

    DEFAULT_BASE_URL = "https://api.anthropic.com"
    DEFAULT_MAX_TOKENS = 8192

    def __init__(self, config: ProviderConfig, provider_settings: Dict[str, Any] | None = None):
        super().__init__(config)
        if provider_settings is not None:
            self.provider_settings = provider_settings
        self._stream_usage_map: Dict[str, Dict[str, Any]] = {}

    def _get_default_base_url(self) -> str:
        return self.config.get("anthropic_base_url", self.DEFAULT_BASE_URL)

    def _get_default_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        api_key = self.config.get("api_key")
        if api_key:
            if not self._validate_api_key(api_key):
                raise ValueError("Invalid Anthropic API key format.")
            headers["x-api-key"] = api_key
        if self.config.get("anthropic_beta_1m_context"):
            headers["anthropic-beta"] = "context-1m-2025-08-07"
        return headers

    async def _fetch_models(self) -> List[ModelInfo]:
        config_models_file = self.config.get("anthropic_models_file")
        if config_models_file:
            models_file = config_models_file
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            models_file = os.path.join(current_dir, "anthropic_models.json")

        try:
            with open(models_file, "r", encoding="utf-8") as f:
                models_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

        models = []
        models_data = models_config.get("models", [])
        for model_data in models_data:
            tiers = model_data.get("tiers", [])
            if tiers:
                pricing_data = tiers[0]
                pricing = PricingInfo(
                    input_price=pricing_data.get("input_price", 0),
                    output_price=pricing_data.get("output_price", 0),
                    cache_writes_price=pricing_data.get("cache_writes_price", 0),
                    cache_reads_price=pricing_data.get("cache_reads_price", 0),
                )
                context_window = pricing_data.get("context_window", 200000)
            else:
                pricing = PricingInfo(
                    input_price=0,
                    output_price=0,
                    cache_writes_price=0,
                    cache_reads_price=0,
                )
                context_window = 200000

            models.append(
                ModelInfo(
                    id=model_data.get("id", ""),
                    name=model_data.get("name", model_data.get("id", "")),
                    max_tokens=model_data.get("max_tokens", self.DEFAULT_MAX_TOKENS),
                    context_window=context_window,
                    capabilities=ModelCapabilities(**model_data.get("capabilities", {})),
                    pricing=pricing,
                    tiers=[ServiceTier(**tier) for tier in tiers],
                )
            )
        return models

    async def text_chat(self, request, **kwargs) -> ApiResponse:
        params = self._build_request_params(request)
        response = await self._request("/v1/messages", body=params, method="POST")
        return self._transform_response(response, request.model)

    async def text_chat_stream(self, request, **kwargs) -> AsyncIterable[ChatChunk]:
        request_body = {**self._build_request_params(request), "stream": True}
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/v1/messages",
            headers=self.default_headers,
            json=request_body,
        ) as response:
            if not response.ok:
                raise ApiError(response.status, await response.text())

            buffer = b""
            max_buffer_size = 10 * 1024 * 1024

            async for chunk in response.content.iter_any():
                buffer += chunk
                if len(buffer) > max_buffer_size:
                    raise RuntimeError(
                        f"Streaming buffer too large: {len(buffer)} bytes"
                    )

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        try:
                            parsed = json.loads(data)
                            transformed_chunk = self._transform_chunk(
                                parsed, request.model
                            )
                            if transformed_chunk:
                                yield transformed_chunk
                        except json.JSONDecodeError:
                            continue

    def _build_request_params(self, request) -> Dict[str, Any]:
        model_id = request.model
        params: Dict[str, Any] = {
            "model": model_id,
            "max_tokens": request.max_tokens
            or self.get_max_output_tokens(model_id, self.config),
            "messages": self._transform_messages(request.messages),
        }
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.tools is not None:
            params["tools"] = request.tools
        if request.tool_choice is not None:
            params["tool_choice"] = request.tool_choice
        if request.system is not None:
            params["system"] = request.system

        reasoning_budget = request.reasoning_budget
        model_info = self._get_model(model_id)
        if (
            reasoning_budget
            and model_info
            and self._should_use_reasoning_budget(model_info, self.config)
        ):
            params["reasoning_budget"] = reasoning_budget
        return params

    def _transform_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
        transformed = []
        for msg_data in messages:
            msg = ChatMessage(**msg_data) if isinstance(msg_data, dict) else msg_data
            if msg.role == "tool":
                transformed.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )
                continue

            if isinstance(msg.content, str):
                content_list = [{"type": "text", "text": msg.content}]
            else:
                content_list = []
                for item in msg.content:
                    if item.get("type") == "image_url":
                        image_data = item["image_url"]["url"]
                        try:
                            header, base64_data = image_data.split(",", 1
                            )
                            if "base64" not in header:
                                continue
                            media_type = header.split(";")[0].split(":")[1]
                            content_list.append(
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": base64_data,
                                    },
                                }
                            )
                        except (ValueError, IndexError):
                            continue
                    else:
                        content_list.append(item)

            transformed_message = {"role": msg.role, "content": content_list}
            if msg.tool_calls:
                transformed_message["tool_calls"] = msg.tool_calls
            transformed.append(transformed_message)
        return transformed

    def _transform_response(self, response: Dict[str, Any], model: str) -> ApiResponse:
        usage_data = response.get("usage", {})
        content_blocks = response.get("content", [])
        text_content = ""
        tool_calls = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )

        message = ChatMessage(
            role="assistant",
            content=text_content,
            tool_calls=tool_calls if tool_calls else None,
        )

        return ApiResponse(
            id=response.get("id"),
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[
                ChatChoice(
                    index=0,
                    message=message,
                    finish_reason=response.get("stop_reason"),
                )
            ],
            usage=TokenUsage(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("input_tokens", 0)
                + usage_data.get("output_tokens", 0),
                cache_creation_input_tokens=usage_data.get(
                    "cache_creation_input_tokens"
                ),
                cache_read_input_tokens=usage_data.get("cache_read_input_tokens"),
            ),
        )

    def _transform_chunk(
        self, chunk: Dict[str, Any], model: str
    ) -> Optional[ChatChunk]:
        chunk_type = chunk.get("type")
        chunk_id = chunk.get("id", f"anthropic-chunk-{int(time.time())}")
        if chunk_type == "message_start":
            self._stream_usage_map[chunk_id] = chunk.get("message", {}).get(
                "usage", {}
            )
            return None

        if chunk_type == "message_delta":
            finish_reason = chunk.get("delta", {}).get("stop_reason")
        elif chunk_type == "message_stop":
            finish_reason = chunk.get("stop_reason")
            if chunk_id in self._stream_usage_map:
                del self._stream_usage_map[chunk_id]
        else:
            finish_reason = None

        delta = {}
        if chunk_type == "content_block_delta":
            delta_content = chunk.get("delta", {})
            if delta_content.get("type") == "text_delta":
                delta = {"content": delta_content.get("text", "")}

        if not delta and not finish_reason:
            return None

        return ChatChunk(
            id=chunk_id,
            object="chat.completion.chunk",
            created=int(time.time()),
            model=model,
            choices=[
                {
                    "index": chunk.get("index", 0),
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        )

    def _requires_api_key(self) -> bool:
        return True

    def _is_anthropic_style(self) -> bool:
        return True

    def _should_use_reasoning_budget(
        self, model: ModelInfo, config: Optional[ProviderConfig] = None
    ) -> bool:
        if not model.capabilities.supports_reasoning_budget:
            return False
        enable_effort = config and config.get("enable_reasoning_effort")
        return bool(model.capabilities.required_reasoning_budget or enable_effort)

    def _validate_api_key(self, api_key: str) -> bool:
        import re

        if not isinstance(api_key, str):
            return False

        is_test_env = os.environ.get("TESTING", "false").lower() == "true"
        if is_test_env:
            if len(api_key) < 10:
                return False
            test_pattern = r"^sk-ant-[a-zA-Z0-9_-]+$"
            return bool(re.match(test_pattern, api_key))

        if len(api_key) < 20:
            return False
        pattern = r"^sk-ant-api03-[a-zA-Z0-9_-]{95,}$"
        if not re.match(pattern, api_key):
            old_pattern = r"^sk-[a-zA-Z0-9_-]{20,}$"
            return bool(re.match(old_pattern, api_key))
        return True
