import abc
from collections.abc import AsyncIterable
from typing import Any, Dict, List, Optional

from .entities import (
    ApiResponse,
    ChatChunk,
    LLMResponse,
    ModelInfo,
    ProviderMeta,
    ProviderRequest,
    RerankResult,
    TokenUsage,
    ValidationResult,
)
from .register import provider_cls_map


class AbstractProvider(abc.ABC):
    """Provider abstract class."""

    def __init__(self, provider_config: Dict[str, Any]) -> None:
        super().__init__()
        self.model_name = ""
        self.provider_config = provider_config

    def set_model(self, model_name: str) -> None:
        self.model_name = model_name

    def get_model(self) -> str:
        return self.model_name

    def meta(self) -> ProviderMeta:
        provider_type_name = self.provider_config["type"]
        meta_data = provider_cls_map.get(provider_type_name)
        if not meta_data:
            raise ValueError(f"Provider type {provider_type_name} not registered")
        return ProviderMeta(
            id=self.provider_config.get("id", "default"),
            model=self.get_model(),
            type=provider_type_name,
            provider_type=meta_data.provider_type,
        )

    async def test(self) -> None:
        ...


class Provider(AbstractProvider):
    """Chat completion provider."""

    def __init__(self, provider_config: Dict[str, Any], provider_settings: Dict[str, Any]) -> None:
        super().__init__(provider_config)
        self.provider_settings = provider_settings

    @abc.abstractmethod
    def get_current_key(self) -> str:
        raise NotImplementedError

    def get_keys(self) -> List[str]:
        keys = self.provider_config.get("key", [""])
        return keys or [""]

    @abc.abstractmethod
    def set_key(self, key: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_models(self) -> List[ModelInfo]:
        raise NotImplementedError

    @abc.abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        raise NotImplementedError

    @abc.abstractmethod
    async def text_chat(self, request: ProviderRequest, **kwargs: Any) -> ApiResponse:
        raise NotImplementedError

    @abc.abstractmethod
    async def text_chat_stream(
        self, request: ProviderRequest, **kwargs: Any
    ) -> AsyncIterable[ChatChunk]:
        if False:  # pragma: no cover - make this an async generator for typing
            yield ChatChunk(id="", object="", created=0, model="", choices=[])
        raise NotImplementedError

    @abc.abstractmethod
    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        raise NotImplementedError

    @abc.abstractmethod
    def get_max_output_tokens(self, model: str, config: Optional[Dict[str, Any]] = None) -> int:
        raise NotImplementedError


class EmbeddingProvider(AbstractProvider):
    def __init__(self, provider_config: Dict[str, Any], provider_settings: Dict[str, Any]) -> None:
        super().__init__(provider_config)
        self.provider_settings = provider_settings

    @abc.abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        ...

    @abc.abstractmethod
    async def get_embeddings(self, text: List[str]) -> List[List[float]]:
        ...

    @abc.abstractmethod
    def get_dim(self) -> int:
        ...


class RerankProvider(AbstractProvider):
    def __init__(self, provider_config: Dict[str, Any], provider_settings: Dict[str, Any]) -> None:
        super().__init__(provider_config)
        self.provider_settings = provider_settings

    @abc.abstractmethod
    async def rerank(self, query: str, documents: List[str], top_n: Optional[int] = None) -> List[RerankResult]:
        ...
