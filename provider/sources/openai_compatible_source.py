import json
import logging
from typing import Dict, Any, List, Optional

from ..base import ApiError
from ..entities import ModelCapabilities, ModelInfo, PricingInfo, ProviderConfig
from ..register import register_provider_adapter
from .openai_source import ProviderOpenAI


@register_provider_adapter(
    "openai_compatible_chat_completion",
    desc="OpenAI compatible chat completion provider",
)
class ProviderOpenAICompatible(ProviderOpenAI):
    """OpenAI-compatible provider adapter using a configurable base URL."""

    DEFAULT_BASE_URL = ""

    def _get_default_base_url(self) -> str:
        base_url = self.config.get("openai_compatible_base_url")
        if not base_url:
            raise ValueError("openai_compatible_base_url is required")
        return self._normalize_base_url(base_url)

    def _normalize_base_url(self, base_url: str) -> str:
        base_url = base_url.strip().rstrip("/")
        if base_url.endswith("/v1"):
            return f"{base_url}/"
        return f"{base_url}/v1/"

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
            return await super()._fetch_models()
        except Exception:
            model_id = self.config.get("openai_model_id") or "unknown"
            return [
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    max_tokens=self.DEFAULT_MAX_TOKENS,
                    context_window=self.DEFAULT_CONTEXT_WINDOW,
                    capabilities=ModelCapabilities(
                        supports_images=True,
                        supports_prompt_cache=False,
                        supports_temperature=True,
                    ),
                    pricing=PricingInfo(input_price=0, output_price=0),
                    description="OpenAI compatible model",
                )
            ]

    async def _request(self, endpoint: str, **kwargs) -> Any:
        return await super()._request(endpoint.lstrip("/"), **kwargs)

    async def text_chat_stream(self, request, **kwargs):
        payload = {**self._build_request_params(request), "stream": True}
        session = await self._get_session()
        base_url = self.base_url.rstrip("/")
        async with session.post(
            f"{base_url}/chat/completions",
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


@register_provider_adapter(
    "groq_chat_completion",
    desc="Groq chat completion provider (OpenAI compatible)",
)
class ProviderGroq(ProviderOpenAICompatible):
    """Groq provider adapter (OpenAI compatible)."""

    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"

    def _get_default_base_url(self) -> str:
        return self.config.get("groq_base_url", self.DEFAULT_BASE_URL)


@register_provider_adapter(
    "zhipu_chat_completion",
    desc="Zhipu chat completion provider (OpenAI compatible)",
)
class ProviderZhipu(ProviderOpenAICompatible):
    """Zhipu provider adapter (OpenAI compatible)."""

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

    def _get_default_base_url(self) -> str:
        return self.config.get("zhipu_base_url", self.DEFAULT_BASE_URL)
