import json
import logging
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
    "openai_chat_completion",
    desc="OpenAI chat completion provider",
)
class ProviderOpenAI(BaseModelAdapter):
    """OpenAI provider adapter."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_CONTEXT_WINDOW = 8192

    def __init__(self, config: ProviderConfig, provider_settings: Dict[str, Any] | None = None):
        super().__init__(config)
        if provider_settings is not None:
            self.provider_settings = provider_settings
        self.logger = logging.getLogger(__name__)

    def _get_default_base_url(self) -> str:
        return self.config.get("openai_base_url", self.DEFAULT_BASE_URL)

    def _get_default_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self.config.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        custom_headers = self.config.get("openai_headers")
        if isinstance(custom_headers, dict) and custom_headers:
            headers.update({str(k): str(v) for k, v in custom_headers.items()})
        return headers

    async def _fetch_models(self) -> List[ModelInfo]:
        try:
            response = await self._request("/models", method="GET")
        except ApiError as exc:
            self.logger.error("Failed to fetch OpenAI models: %s", exc.message)
            return []

        models: List[ModelInfo] = []
        for model_data in response.get("data", []):
            model_id = model_data.get("id")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    max_tokens=self.DEFAULT_MAX_TOKENS,
                    context_window=self.DEFAULT_CONTEXT_WINDOW,
                    capabilities=ModelCapabilities(
                        supports_images="vision" in model_id or "gpt-4o" in model_id,
                        supports_prompt_cache=False,
                        supports_temperature=True,
                    ),
                    pricing=PricingInfo(input_price=0, output_price=0),
                    description=model_data.get("description") or model_data.get("object"),
                )
            )

        return models

    async def text_chat(self, request, **kwargs) -> ApiResponse:
        payload = self._build_request_params(request)
        response = await self._request("/chat/completions", body=payload, method="POST")
        return self._transform_response(response)

    async def text_chat_stream(self, request, **kwargs) -> AsyncIterable[ChatChunk]:
        payload = {**self._build_request_params(request), "stream": True}
        session = await self._get_session()
        async with session.post(
            f"{self.base_url}/chat/completions",
            headers=self.default_headers,
            json=payload,
        ) as response:
            if not response.ok:
                raise ApiError(response.status, await response.text())

            async for line in response.content.iter_lines():
                if not line:
                    continue
                try:
                    line = line.decode("utf-8").strip() if isinstance(line, bytes) else line.strip()
                except UnicodeDecodeError:
                    continue
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    return
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue
                yield self._transform_chunk(parsed)

    def _build_request_params(self, request) -> Dict[str, Any]:
        messages = self._transform_messages(request.messages)
        if request.system:
            messages = [{"role": "system", "content": request.system}, *messages]

        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens
            or self.get_max_output_tokens(request.model, self.config),
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        return payload

    def _transform_messages(self, messages: List[Any]) -> List[Dict[str, Any]]:
        transformed = []
        for msg_data in messages:
            msg = ChatMessage(**msg_data) if isinstance(msg_data, dict) else msg_data
            payload: Dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }
            if msg.role == "tool":
                payload["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                payload["tool_calls"] = msg.tool_calls
            transformed.append(payload)
        return transformed

    def _transform_response(self, response: Dict[str, Any]) -> ApiResponse:
        usage_data = response.get("usage")
        usage = self._build_token_usage(usage_data) if usage_data else None
        return ApiResponse(
            id=response.get("id"),
            object=response.get("object", "chat.completion"),
            created=response.get("created", 0),
            model=response.get("model", ""),
            choices=[
                ChatChoice(
                    index=choice.get("index", 0),
                    message=self._build_chat_message(choice.get("message")) if choice.get("message") else None,
                    finish_reason=choice.get("finish_reason"),
                )
                for choice in response.get("choices", [])
            ],
            usage=usage,
        )

    def _build_token_usage(self, usage_data: Dict[str, Any]) -> Optional[TokenUsage]:
        if not isinstance(usage_data, dict):
            return None
        return TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens"),
            cache_read_input_tokens=usage_data.get("cache_read_input_tokens"),
        )

    def _build_chat_message(self, message: Dict[str, Any]) -> ChatMessage:
        if not isinstance(message, dict):
            return ChatMessage(role="assistant", content="")
        return ChatMessage(
            role=message.get("role", "assistant"),
            content=message.get("content", ""),
            tool_calls=message.get("tool_calls"),
            tool_call_id=message.get("tool_call_id"),
        )

    def _transform_chunk(self, chunk: Dict[str, Any]) -> ChatChunk:
        return ChatChunk(
            id=chunk.get("id"),
            object=chunk.get("object", "chat.completion.chunk"),
            created=chunk.get("created", 0),
            model=chunk.get("model", ""),
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
