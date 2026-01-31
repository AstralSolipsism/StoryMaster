import json
import logging
import os
from typing import AsyncIterable, Dict, Any, List, Optional

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
    TokenUsage,
)
from ..register import register_provider_adapter


@register_provider_adapter(
    "openrouter_chat_completion",
    desc="OpenRouter chat completion provider",
)
class ProviderOpenRouter(BaseModelAdapter):
    """OpenRouter provider adapter."""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MAX_TOKENS = 4096

    def __init__(self, config: ProviderConfig, provider_settings: Dict[str, Any] | None = None):
        super().__init__(config)
        if provider_settings is not None:
            self.provider_settings = provider_settings
        self.logger = logging.getLogger(__name__)

    def _get_default_base_url(self) -> str:
        return self.config.get("openrouter_base_url", self.DEFAULT_BASE_URL)

    def _get_default_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}

        http_referer = self.config.get("http_referer") or os.environ.get("HTTP_REFERER")
        if http_referer:
            headers["HTTP-Referer"] = http_referer

        app_name = self.config.get("x_title") or os.environ.get("APP_NAME")
        if app_name:
            headers["X-Title"] = app_name

        api_key = self.config.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            api_key = None

        return headers

    async def _fetch_models(self) -> List[ModelInfo]:
        try:
            response = await self._request("/models", method="GET")
        except ApiError as exc:
            self.logger.error("Failed to fetch OpenRouter models: %s", exc.message)
            return []

        models = []
        for model_data in response.get("data", []):
            if not model_data.get("id") or not model_data.get("context_length"):
                continue

            pricing = model_data.get("pricing", {})
            capabilities_data = model_data.get("architecture", {})
            models.append(
                ModelInfo(
                    id=model_data.get("id"),
                    name=model_data.get("name", model_data.get("id")),
                    max_tokens=model_data.get("top_provider", {}).get("max_completion_tokens")
                    or self.DEFAULT_MAX_TOKENS,
                    context_window=model_data.get("context_length"),
                    capabilities=ModelCapabilities(
                        supports_images="vision" in capabilities_data.get("modality", ""),
                        supports_prompt_cache=capabilities_data.get("prompt_caching", False),
                        supports_reasoning_budget=capabilities_data.get("reasoning_budget", False),
                    ),
                    pricing=PricingInfo(
                        input_price=float(pricing.get("prompt", 0)) * 1_000_000,
                        output_price=float(pricing.get("completion", 0)) * 1_000_000,
                        cache_writes_price=float(pricing.get("cache_write", {}).get("prompt", 0))
                        * 1_000_000,
                        cache_reads_price=float(pricing.get("cache_read", {}).get("prompt", 0))
                        * 1_000_000,
                    ),
                    description=model_data.get("description"),
                )
            )

        return models

    async def text_chat(self, request, **kwargs) -> ApiResponse:
        request_body = self._build_request_params(request)
        response = await self._request("/chat/completions", body=request_body, method="POST")
        return self._transform_response(response)

    async def text_chat_stream(self, request, **kwargs) -> AsyncIterable[ChatChunk]:
        request_body = {**self._build_request_params(request), "stream": True}
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/chat/completions",
            headers=self.default_headers,
            json=request_body,
        ) as response:
            if not response.ok:
                raise ApiError(response.status, await response.text())

            json_decode_errors = 0
            unicode_decode_errors = 0

            async for line in response.content.iter_lines():
                try:
                    line = line.decode("utf-8").strip() if isinstance(line, bytes) else line.strip()
                except UnicodeDecodeError as exc:
                    unicode_decode_errors += 1
                    self.logger.warning("Unicode decode error in stream: %s", exc)
                    continue

                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    try:
                        parsed = json.loads(data)
                        yield self._transform_chunk(parsed)
                    except json.JSONDecodeError as exc:
                        json_decode_errors += 1
                        self.logger.warning(
                            "JSON decode error in stream: %s, data: %s...",
                            exc,
                            data[:100],
                        )
                        continue

            if json_decode_errors > 0:
                self.logger.error("Total JSON decode errors: %s", json_decode_errors)
            if unicode_decode_errors > 0:
                self.logger.error("Total Unicode decode errors: %s", unicode_decode_errors)

    def _build_request_params(self, request) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "max_tokens": request.max_tokens
            or self.get_max_output_tokens(request.model, self.config),
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice

        specific_provider = self.config.get("openrouter_specific_provider")
        use_middle_out_transform = self.config.get("openrouter_use_middle_out_transform", True)

        if specific_provider:
            payload["provider"] = {
                "order": [specific_provider],
                "allow_fallbacks": False,
            }

        if use_middle_out_transform:
            payload["transforms"] = ["middle-out"]

        return payload

    def _transform_response(self, response: Dict[str, Any]) -> ApiResponse:
        usage_data = response.get("usage")
        return ApiResponse(
            id=response.get("id"),
            object="chat.completion",
            created=response.get("created"),
            model=response.get("model"),
            choices=[
                ChatChoice(
                    index=choice.get("index"),
                    message=ChatMessage(**choice.get("message")),
                    finish_reason=choice.get("finish_reason"),
                )
                for choice in response.get("choices", [])
            ],
            usage=TokenUsage(**usage_data) if usage_data else None,
        )

    def _transform_chunk(self, chunk: Dict[str, Any]) -> ChatChunk:
        return ChatChunk(
            id=chunk.get("id"),
            object="chat.completion.chunk",
            created=chunk.get("created"),
            model=chunk.get("model"),
            choices=chunk.get("choices", []),
        )

    def _requires_api_key(self) -> bool:
        return True

    def _is_anthropic_style(self) -> bool:
        return False

    def _should_use_reasoning_budget(
        self, model: ModelInfo, config: Optional[ProviderConfig] = None
    ) -> bool:
        if not model.capabilities.supports_reasoning_budget:
            return False
        enable_effort = config and config.get("enable_reasoning_effort")
        return bool(model.capabilities.required_reasoning_budget or enable_effort)
