import asyncio
import json
import time
import uuid
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
    TokenUsage,
)
from ..register import register_provider_adapter


@register_provider_adapter(
    "ollama_chat_completion",
    desc="Ollama chat completion provider",
)
class ProviderOllama(BaseModelAdapter):
    """Ollama provider adapter."""

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_CONTEXT_WINDOW = 2048

    def __init__(self, config: ProviderConfig, provider_settings: Dict[str, Any] | None = None):
        super().__init__(config)
        if provider_settings is not None:
            self.provider_settings = provider_settings

    def _get_default_base_url(self) -> str:
        return self.config.get("ollama_base_url", self.DEFAULT_BASE_URL)

    def _get_default_headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json"}

    async def _fetch_models(self) -> List[ModelInfo]:
        try:
            response = await self._request("/api/tags", method="GET")
            models = []
            semaphore = asyncio.Semaphore(10)

            async def _limited_request(sema, model_name):
                async with sema:
                    return await self._request(
                        "/api/show", body={"name": model_name}, method="POST"
                    )

            tasks = [
                _limited_request(semaphore, model_data["name"])
                for model_data in response.get("models", [])
            ]
            details_list = await asyncio.gather(*tasks)

            for model_data, details in zip(response.get("models", []), details_list):
                parameter_size = details.get("details", {}).get(
                    "parameter_size", self.DEFAULT_CONTEXT_WINDOW
                )
                context_window = self._parse_parameter_size(parameter_size)

                models.append(
                    ModelInfo(
                        id=model_data.get("name"),
                        name=model_data.get("name"),
                        max_tokens=self.DEFAULT_MAX_TOKENS,
                        context_window=context_window,
                        capabilities=ModelCapabilities(
                            supports_images="clip"
                            in str(details.get("details", {}).get("families")),
                            supports_prompt_cache=False,
                            supports_temperature=True,
                        ),
                        pricing=PricingInfo(input_price=0, output_price=0),
                        description=f"Ollama hosted model: {model_data.get('name')}",
                    )
                )

            return models
        except (aiohttp.ClientError, json.JSONDecodeError, asyncio.TimeoutError) as error:
            return []

    async def text_chat(self, request, **kwargs) -> ApiResponse:
        request_body = self._build_request_params(request)
        response = await self._request("/api/chat", body=request_body, method="POST")
        return self._transform_response(response, request.model)

    async def text_chat_stream(self, request, **kwargs) -> AsyncIterable[ChatChunk]:
        request_body = {**self._build_request_params(request), "stream": True}
        timeout = aiohttp.ClientTimeout(total=self.config.get("timeout", 60))
        connector = aiohttp.TCPConnector(ssl=True)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                headers=self.default_headers,
                json=request_body,
            ) as response:
                if not response.ok:
                    raise ApiError(response.status, await response.text())

                async for line in response.content:
                    line = line.decode("utf-8", errors="replace").strip()
                    if line:
                        try:
                            parsed = json.loads(line)
                            yield self._transform_chunk(parsed)
                        except json.JSONDecodeError:
                            continue

    def _build_request_params(self, request) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens
                or self.get_max_output_tokens(request.model, self.config),
            },
        }
        num_ctx = self.config.get("ollama_num_ctx")
        if num_ctx:
            payload["options"]["num_ctx"] = num_ctx
        return payload

    def _transform_response(self, response: Dict[str, Any], model: str) -> ApiResponse:
        message = ChatMessage(role="assistant", content=response.get("message", {}).get("content", ""))
        choice = ChatChoice(
            index=0,
            message=message,
            finish_reason="stop" if response.get("done") else "length",
        )
        return ApiResponse(
            id=f"ollama-{uuid.uuid4()}",
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[choice],
            usage=TokenUsage(
                prompt_tokens=response.get("prompt_eval_count", 0),
                completion_tokens=response.get("eval_count", 0),
                total_tokens=response.get("prompt_eval_count", 0)
                + response.get("eval_count", 0),
            ),
        )

    def _transform_chunk(self, chunk: Dict[str, Any]) -> ChatChunk:
        return ChatChunk(
            id=f"ollama-chunk-{uuid.uuid4()}",
            object="chat.completion.chunk",
            created=int(time.time()),
            model=chunk.get("model"),
            choices=[
                {
                    "index": 0,
                    "delta": {"content": chunk.get("message", {}).get("content", "")},
                    "finish_reason": "stop" if chunk.get("done") else None,
                }
            ],
        )

    def _requires_api_key(self) -> bool:
        return False

    def _is_anthropic_style(self) -> bool:
        return False

    def _parse_parameter_size(self, parameter_size) -> int:
        if isinstance(parameter_size, (int, float)):
            return int(parameter_size)
        if isinstance(parameter_size, str):
            import re

            match = re.search(r"(\d+\.?\d*)", parameter_size.strip().upper())
            if match:
                number_str = match.group(1)
                try:
                    number = float(number_str)
                    if "B" in parameter_size.upper():
                        return int(number * 6000)
                    if "M" in parameter_size.upper():
                        return int(number * 6)
                    if "K" in parameter_size.upper():
                        return max(int(number / 1000 * 6000), 1024)
                    return int(number)
                except ValueError:
                    pass
        return self.DEFAULT_CONTEXT_WINDOW

    def _should_use_reasoning_budget(
        self, model: ModelInfo, config: Optional[ProviderConfig] = None
    ) -> bool:
        return False
