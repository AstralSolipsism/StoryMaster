import aiohttp
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .entities import ModelInfo, ProviderConfig, TokenUsage, ValidationResult
from .provider import Provider
from ..core.logging import log_exception_alert, get_logger


class ApiError(Exception):
    """API error wrapper."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"API Error {status}: {message}")


class BaseHttpClient(ABC):
    """HTTP client base class."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.base_url = config.get("base_url") or self._get_default_base_url()
        self.default_headers = self._get_default_headers()
        self._session: Optional[aiohttp.ClientSession] = None

    @abstractmethod
    def _get_default_base_url(self) -> str:
        pass

    @abstractmethod
    def _get_default_headers(self) -> Dict[str, str]:
        pass

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(
                total=self.config.get("timeout", 30), connect=10
            )
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _request(self, endpoint: str, **kwargs) -> Any:
        from urllib.parse import urljoin

        url = urljoin(self.base_url, endpoint)
        request_options = self._create_request_options(
            kwargs.get("body"), kwargs.get("headers")
        )

        session = await self._get_session()

        try:
            async with session.request(
                method=kwargs.get("method", "POST"),
                url=url,
                headers=request_options["headers"],
                json=request_options["body"],
                timeout=request_options["timeout"],
            ) as response:
                if not response.ok:
                    error_text = await response.text()
                    raise ApiError(response.status, error_text)
                try:
                    return await response.json()
                except Exception as exc:
                    raise ApiError(500, f"JSON parse error: {str(exc)}")
        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError):
            logger = get_logger("provider")
            log_exception_alert(
                logger,
                "LLM provider request timeout",
                alert_code="LLM_REQUEST_TIMEOUT",
                severity="error",
                endpoint=endpoint,
                base_url=self.base_url,
            )
            raise ApiError(408, "Request timeout")
        except aiohttp.ClientError as exc:
            logger = get_logger("provider")
            log_exception_alert(
                logger,
                "LLM provider client error",
                alert_code="LLM_CLIENT_ERROR",
                severity="error",
                endpoint=endpoint,
                base_url=self.base_url,
                error=str(exc),
            )
            raise ApiError(500, f"Client error: {str(exc)}")

    def _create_request_options(
        self, body: Any, custom_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        return {
            "headers": {**self.default_headers, **(custom_headers or {})},
            "body": body,
            "timeout": None,
        }


class BaseModelAdapter(BaseHttpClient, Provider):
    """Base class for chat providers."""

    def __init__(self, config: ProviderConfig):
        BaseHttpClient.__init__(self, config)
        self.provider_settings: Dict[str, Any] = {}
        self.models: Dict[str, ModelInfo] = {}
        self._current_key: str = ""

    def get_current_key(self) -> str:
        return self._current_key

    def set_key(self, key: str) -> None:
        self._current_key = key

    async def get_models(self) -> List[ModelInfo]:
        if not self.models:
            if not hasattr(self, "_models_lock"):
                self._models_lock = asyncio.Lock()
            async with self._models_lock:
                if not self.models:
                    models = await self._fetch_models()
                    self.models = {model.id: model for model in models}
        return list(self.models.values())

    def _get_model(self, model_id: str) -> Optional[ModelInfo]:
        return self.models.get(model_id)

    def validate_config(self, config: ProviderConfig) -> ValidationResult:
        errors = []
        if not config.get("api_key") and self._requires_api_key():
            errors.append("需要API密钥")

        base_url = config.get("base_url")
        if base_url and not self._is_valid_url(base_url):
            errors.append("无效的基础URL")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        model_info = self._get_model(model)
        if not model_info or not model_info.pricing or not usage:
            return 0.0

        pricing = model_info.pricing
        input_price = pricing.input_price or 0.0
        output_price = pricing.output_price or 0.0
        cache_writes_price = pricing.cache_writes_price or 0.0
        cache_reads_price = pricing.cache_reads_price or 0.0

        input_cost = (usage.prompt_tokens / 1_000_000) * input_price
        output_cost = (usage.completion_tokens / 1_000_000) * output_price

        cache_cost = 0.0
        if usage.cache_creation_input_tokens and cache_writes_price:
            cache_cost += (usage.cache_creation_input_tokens / 1_000_000) * cache_writes_price
        if usage.cache_read_input_tokens and cache_reads_price:
            cache_cost += (usage.cache_read_input_tokens / 1_000_000) * cache_reads_price

        return input_cost + output_cost + cache_cost

    def get_max_output_tokens(self, model: str, config: Optional[ProviderConfig] = None) -> int:
        model_info = self._get_model(model)
        if not model_info:
            return 4096

        if not model_info.capabilities:
            return model_info.max_tokens or 4096

        if self._should_use_reasoning_budget(model_info, config):
            return config.get("model_max_tokens", 16384) if config else 16384

        if model_info.capabilities.supports_reasoning_budget and self._is_anthropic_style():
            return 8192

        return model_info.max_tokens or 4096

    @abstractmethod
    async def _fetch_models(self) -> List[ModelInfo]:
        pass

    @abstractmethod
    def _requires_api_key(self) -> bool:
        pass

    def _is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except (ValueError, TypeError):
            return False

    @abstractmethod
    def _is_anthropic_style(self) -> bool:
        pass

    @abstractmethod
    def _should_use_reasoning_budget(
        self, model: ModelInfo, config: Optional[ProviderConfig] = None
    ) -> bool:
        pass
