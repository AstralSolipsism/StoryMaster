import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncIterable, Tuple

from .entities import (
    ApiResponse,
    ChatChunk,
    ChatMessage,
    ModelInfo,
    ProviderConfig,
    ProviderRequest,
    ProviderType,
    TokenUsage,
    ValidationResult,
)
from .provider import Provider
from .register import provider_cls_map
from ..core.logging import log_llm_traffic, log_exception_alert, llm_logger, get_logger


@dataclass
class ProviderManagerConfig:
    default_provider: str
    fallback_providers: Optional[List[str]] = None
    max_retries: int = 3
    retry_delay: int = 1
    enable_load_balancing: bool = False
    cost_threshold: Optional[float] = None
    high_priority_latency_threshold: int = 5000
    DEFAULT_LATENCIES: Dict[str, int] = field(
        default_factory=lambda: {
            "openai_chat_completion": 2500,
            "openai_compatible_chat_completion": 2500,
            "groq_chat_completion": 2000,
            "zhipu_chat_completion": 2500,
            "anthropic_chat_completion": 2000,
            "openrouter_chat_completion": 3000,
            "ollama_chat_completion": 500,
        }
    )


@dataclass
class ScheduleResult:
    provider: Provider
    model: str
    provider_name: str
    estimated_cost: float
    estimated_latency: int


@dataclass
class CandidateProvider:
    provider: Provider
    provider_name: str
    model: str
    estimated_cost: float
    estimated_latency: int
    score: float


@dataclass
class ProviderMetrics:
    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_latency: int = 0
    average_latency: float = 0.0
    total_cost: float = 0.0


class ProviderManager:
    """Unified provider manager for chat completion providers."""

    def __init__(
        self,
        config: ProviderManagerConfig,
        provider_configs: Dict[str, ProviderConfig] | None = None,
    ) -> None:
        self.config = config
        self.provider_configs = provider_configs or {}
        self.providers: Dict[str, Provider] = {}
        self.metrics: Dict[str, ProviderMetrics] = {}
        self.model_cache: Dict[str, Tuple[List[ModelInfo], float]] = {}
        self.cache_ttl: int = 600
        self._cache_cleanup_task: Optional[asyncio.Task] = None
        self.metrics_lock = asyncio.Lock()
        self._logger = get_logger("provider")

    async def initialize(self) -> None:
        logging.info("Initializing providers: registry=%s", ",".join(sorted(provider_cls_map.keys())) or "none")
        allowed = set(self.provider_configs.keys()) if self.provider_configs else None
        for provider_name, meta in provider_cls_map.items():
            if meta.provider_type != ProviderType.CHAT_COMPLETION:
                continue
            if allowed is not None and provider_name not in allowed:
                logging.debug("Skipping provider %s (not in active config)", provider_name)
                continue
            try:
                config = self._get_provider_config(provider_name)
                validation = None
                if meta.default_config_tmpl and meta.default_config_tmpl.get("enable") is False:
                    validation = ValidationResult(is_valid=False, errors=["disabled by config"])
                if validation is None:
                    provider = meta.cls_type(config, self.provider_configs)
                else:
                    provider = None
                if provider and hasattr(provider, "validate_config"):
                    validation = provider.validate_config(config)
                if isinstance(validation, ValidationResult) and not validation.is_valid:
                    logging.warning(
                        "Failed to initialize %s: %s",
                        provider_name,
                        validation.errors,
                    )
                    continue
                if provider and hasattr(provider, "get_models"):
                    try:
                        await provider.get_models()
                    except Exception:
                        logging.debug("Model prefetch failed for %s", provider_name)
                if provider:
                    self.providers[provider_name] = provider
                    logging.info("Initialized provider: %s", provider_name)
            except Exception:
                logging.error("Error initializing provider %s", provider_name, exc_info=True)

        if self.providers and self.config.default_provider not in self.providers:
            fallback_provider = next(iter(self.providers.keys()))
            logging.warning(
                "Default provider %s is not initialized; falling back to %s",
                self.config.default_provider,
                fallback_provider,
            )
            self.config.default_provider = fallback_provider

        self._cache_cleanup_task = asyncio.create_task(self._cache_cleanup_loop())

    async def schedule(self, context: ProviderRequest) -> ScheduleResult:
        provider_name = self.config.default_provider
        provider = self.providers.get(provider_name)
        if not provider:
            available = ", ".join(sorted(self.providers.keys())) or "none"
            raise ValueError(
                f"Provider {provider_name} is not initialized. Available providers: {available}"
            )

        model = self._resolve_model(provider_name, context)
        await self._ensure_model_available(provider_name, provider, model)

        estimated_cost = 0.0
        if hasattr(provider, "calculate_cost"):
            usage = TokenUsage(
                prompt_tokens=self._estimate_tokens(context.messages),
                completion_tokens=context.max_tokens or 1000,
                total_tokens=self._estimate_tokens(context.messages) + (context.max_tokens or 1000),
            )
            estimated_cost = provider.calculate_cost(model, usage)

        estimated_latency = self._estimate_latency(provider_name)

        return ScheduleResult(
            provider=provider,
            model=model,
            provider_name=provider_name,
            estimated_cost=estimated_cost,
            estimated_latency=estimated_latency,
        )

    async def chat(self, context: ProviderRequest) -> ApiResponse:
        schedule = await self.schedule(context)
        start_time = time.monotonic()
        try:
            response = await self._execute_with_retry(
                schedule.provider,
                context,
                schedule.model,
            )
            latency = int((time.monotonic() - start_time) * 1000)
            await self._update_metrics(schedule.provider_name, latency, response)
            self._log_llm_response(schedule.provider_name, context, schedule.model, response, latency)
            return response
        except Exception as error:
            latency = int((time.monotonic() - start_time) * 1000)
            await self._update_metrics(schedule.provider_name, latency, error=error)
            self._log_llm_error(schedule.provider_name, context, schedule.model, latency, error)
            return await self._handle_failure(error, context, schedule)

    async def chat_stream(self, context: ProviderRequest) -> AsyncIterable[ChatChunk]:
        schedule = await self.schedule(context)
        start_time = time.monotonic()
        response_parts: List[str] = []
        try:
            self._log_llm_request(schedule.provider_name, context, schedule.model)
            stream = schedule.provider.text_chat_stream(
                self._build_provider_request(context, schedule.model)
            )
            async for chunk in stream:
                response_parts.append(self._extract_chunk_content(chunk))
                yield chunk
            latency = int((time.monotonic() - start_time) * 1000)
            await self._update_metrics(schedule.provider_name, latency)
            self._log_llm_stream_complete(
                schedule.provider_name,
                context,
                schedule.model,
                latency,
                response_text="".join(response_parts),
            )
        except Exception as error:
            latency = int((time.monotonic() - start_time) * 1000)
            await self._update_metrics(schedule.provider_name, latency, error=error)
            self._log_llm_error(schedule.provider_name, context, schedule.model, latency, error)
            async for chunk in self._handle_stream_failure(error, context, schedule):
                yield chunk

    async def _find_candidates(self, context: ProviderRequest) -> List[CandidateProvider]:
        candidates: List[CandidateProvider] = []
        for provider_name, provider in self.providers.items():
            try:
                cached_models, timestamp = self.model_cache.get(provider_name, (None, 0))
                if cached_models and time.monotonic() - timestamp < self.cache_ttl:
                    models = cached_models
                else:
                    models = await provider.get_models()
                    self.model_cache[provider_name] = (models, time.monotonic())

                suitable_models = self._find_suitable_models(models, context)
                for model in suitable_models:
                    if context.model and model != context.model:
                        continue

                    estimated_cost = 0.0
                    if hasattr(provider, "calculate_cost"):
                        usage = TokenUsage(
                            prompt_tokens=self._estimate_tokens(context.messages),
                            completion_tokens=context.max_tokens or 1000,
                            total_tokens=self._estimate_tokens(context.messages)
                            + (context.max_tokens or 1000),
                        )
                        estimated_cost = provider.calculate_cost(model, usage)

                    estimated_latency = self._estimate_latency(provider_name)

                    candidates.append(
                        CandidateProvider(
                            provider=provider,
                            provider_name=provider_name,
                            model=model,
                            estimated_cost=estimated_cost,
                            estimated_latency=estimated_latency,
                            score=self._calculate_score(
                                estimated_cost, estimated_latency, context
                            ),
                        )
                    )
            except Exception as error:
                logging.warning("Failed to get models from %s: %s", provider_name, error)

        return sorted(candidates, key=lambda x: x.score, reverse=True)

    def _resolve_model(self, provider_name: str, context: ProviderRequest) -> str:
        if context.model:
            return context.model
        provider_config = self._get_provider_config(provider_name)
        model = provider_config.get("model")
        if not model:
            raise ValueError("Model must be specified in request or provider profile")
        return model

    async def _ensure_model_available(
        self, provider_name: str, provider: Provider, model: str
    ) -> None:
        if not hasattr(provider, "get_models"):
            return
        try:
            models = await provider.get_models()
        except Exception as error:
            logging.warning("Failed to fetch models for %s: %s", provider_name, error)
            return
        if not models:
            return
        model_ids = {m.id for m in models}
        if model not in model_ids:
            raise ValueError(f"Model {model} is not available for provider {provider_name}")

    def calculate_score(
        self,
        cost: float,
        latency: int,
        priority: str = "medium",
    ) -> float:
        context = ProviderRequest(messages=[ChatMessage(role="system", content="")], priority=priority)
        return self._calculate_score(cost, latency, context)

    def get_estimated_latency(self, provider_name: str) -> int:
        return self._estimate_latency(provider_name)

    def _calculate_score(
        self, cost: float, latency: int, context: ProviderRequest
    ) -> float:
        score = 100.0
        if self.config.cost_threshold and cost > self.config.cost_threshold:
            score -= 50.0
        else:
            score -= min(30.0, cost * 1000)
        score -= min(20.0, latency / 200.0)
        if context.priority == "high":
            score += 20.0
        elif context.priority == "medium":
            score += 10.0
        return max(0.0, score)

    async def _execute_with_retry(
        self, provider: Provider, context: ProviderRequest, model: str
    ) -> ApiResponse:
        last_error: Optional[Exception] = None
        for attempt in range(self.config.max_retries + 1):
            try:
                if attempt == 0:
                    self._log_llm_request(
                        provider_name=self._get_provider_name(provider),
                        context=context,
                        model=model,
                    )
                req = self._build_provider_request(context, model)
                return await provider.text_chat(req)
            except Exception as error:
                last_error = error
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (2**attempt)
                    await asyncio.sleep(delay)
        if last_error:
            raise last_error
        raise RuntimeError("Unknown provider execution error")

    async def _handle_failure(
        self,
        error: Exception,
        context: ProviderRequest,
        schedule: ScheduleResult,
    ) -> ApiResponse:
        logging.warning(
            "Request failed with %s (%s): %s",
            schedule.provider_name,
            schedule.model,
            error,
        )
        log_exception_alert(
            self._logger,
            "LLM provider request failed",
            alert_code="LLM_REQUEST_FAILED",
            severity="error",
            provider=schedule.provider_name,
            model=schedule.model,
            error=str(error),
            user_id=context.user_id,
            session_id=context.session_id,
        )
        last_fallback_error = None
        if self.config.fallback_providers:
            for fallback_provider in self.config.fallback_providers:
                if fallback_provider == schedule.provider_name:
                    continue
                provider = self.providers.get(fallback_provider)
                if not provider:
                    continue
                try:
                    fallback_context = dataclasses.replace(context, model=None)
                    fallback_config = dataclasses.replace(
                        self.config, default_provider=fallback_provider
                    )
                    fallback_manager = ProviderManager(
                        fallback_config, self.provider_configs
                    )
                    fallback_manager.providers = self.providers
                    fallback_schedule = await fallback_manager.schedule(fallback_context)
                    req = self._build_provider_request(context, fallback_schedule.model)
                    return await fallback_schedule.provider.text_chat(req)
                except Exception as fallback_error:
                    logging.warning(
                        "Fallback provider %s failed: %s",
                        fallback_provider,
                        fallback_error,
                    )
                    last_fallback_error = fallback_error

        if last_fallback_error:
            raise last_fallback_error from error
        raise error

    async def _handle_stream_failure(
        self,
        error: Exception,
        context: ProviderRequest,
        schedule: ScheduleResult,
    ) -> AsyncIterable[ChatChunk]:
        logging.warning(
            "Stream failed with %s (%s): %s",
            schedule.provider_name,
            schedule.model,
            error,
        )
        try:
            fallback_response = await self._handle_failure(error, context, schedule)
            if not fallback_response.choices:
                raise ValueError("No choices in fallback response")
            content = (
                fallback_response.choices[0].message.content
                if fallback_response.choices[0].message
                else ""
            )
            content = content or ""
            yield ChatChunk(
                id=fallback_response.id,
                object="chat.completion.chunk",
                created=fallback_response.created,
                model=fallback_response.model,
                choices=[
                    {
                        "index": 0,
                        "delta": {"content": content} if content else {},
                        "finish_reason": None,
                    }
                ],
            )
            yield ChatChunk(
                id=fallback_response.id,
                object="chat.completion.chunk",
                created=fallback_response.created,
                model=fallback_response.model,
                choices=[
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": fallback_response.choices[0].finish_reason
                        or "stop",
                    }
                ],
            )
        except Exception:
            error_message = "ERROR: An unexpected error occurred. Please try again."
            yield ChatChunk(
                id=f"error-{int(time.time())}",
                object="chat.completion.chunk",
                created=int(time.time()),
                model=schedule.model,
                choices=[
                    {
                        "index": 0,
                        "delta": {"content": error_message},
                        "finish_reason": "error",
                    }
                ],
            )

    def _get_provider_config(self, provider_name: str) -> ProviderConfig:
        return self.provider_configs.get(provider_name, {})

    def _log_llm_request(
        self,
        provider_name: str,
        context: ProviderRequest,
        model: str,
    ) -> None:
        log_llm_traffic(
            llm_logger,
            request_id=context.session_id,
            provider=provider_name,
            model=model,
            messages=context.messages,
            request_payload={
                "max_tokens": context.max_tokens,
                "temperature": context.temperature,
                "stream": context.stream,
                "priority": context.priority,
                "tools": context.tools,
                "tool_choice": context.tool_choice,
                "system": context.system,
                "reasoning_budget": context.reasoning_budget,
            },
            status="started",
            user_id=context.user_id,
            session_id=context.session_id,
        )

    def _log_llm_response(
        self,
        provider_name: str,
        context: ProviderRequest,
        model: str,
        response: ApiResponse,
        latency: int,
    ) -> None:
        response_text = ""
        if response and response.choices:
            first_choice = response.choices[0]
            if first_choice.message:
                response_text = first_choice.message.content or ""
        log_llm_traffic(
            llm_logger,
            request_id=context.session_id,
            provider=provider_name,
            model=model,
            messages=context.messages,
            response_payload={
                "id": response.id,
                "object": response.object,
                "created": response.created,
                "choices": [
                    {
                        "index": choice.index,
                        "finish_reason": choice.finish_reason,
                        "message": {
                            "role": choice.message.role if choice.message else None,
                            "content": choice.message.content if choice.message else None,
                            "tool_calls": choice.message.tool_calls if choice.message else None,
                        }
                        if choice.message
                        else None,
                    }
                    for choice in response.choices
                ],
                "usage": response.usage.__dict__ if response.usage else None,
            },
            response_text=response_text,
            latency_ms=latency,
            status="ok",
            user_id=context.user_id,
            session_id=context.session_id,
        )

    def _log_llm_stream_complete(
        self,
        provider_name: str,
        context: ProviderRequest,
        model: str,
        latency: int,
        response_text: Optional[str] = None,
    ) -> None:
        log_llm_traffic(
            llm_logger,
            request_id=context.session_id,
            provider=provider_name,
            model=model,
            messages=context.messages,
            response_text=response_text,
            latency_ms=latency,
            status="stream_complete",
            user_id=context.user_id,
            session_id=context.session_id,
        )

    def _log_llm_error(
        self,
        provider_name: str,
        context: ProviderRequest,
        model: str,
        latency: int,
        error: Exception,
    ) -> None:
        log_llm_traffic(
            llm_logger,
            request_id=context.session_id,
            provider=provider_name,
            model=model,
            messages=context.messages,
            latency_ms=latency,
            status="error",
            error=str(error),
            user_id=context.user_id,
            session_id=context.session_id,
        )

    def _find_suitable_models(
        self, models: List[str], context: ProviderRequest
    ) -> List[str]:
        has_images = any(self._message_has_images(msg) for msg in context.messages)
        if not has_images:
            return models
        return models

    def _estimate_latency(self, provider_name: str) -> int:
        metrics = self.metrics.get(provider_name)
        if metrics and metrics.average_latency > 0:
            return int(metrics.average_latency)
        return self.config.DEFAULT_LATENCIES.get(provider_name, 3000)

    def _build_provider_request(
        self, context: ProviderRequest, model: str
    ) -> ProviderRequest:
        return ProviderRequest(
            messages=context.messages,
            model=model,
            max_tokens=context.max_tokens,
            temperature=context.temperature,
            stream=context.stream,
            priority=context.priority,
            user_id=context.user_id,
            session_id=context.session_id,
            tools=context.tools,
            tool_choice=context.tool_choice,
            system=context.system,
            reasoning_budget=context.reasoning_budget,
        )

    def _get_provider_name(self, provider: Provider) -> str:
        for name, instance in self.providers.items():
            if instance is provider:
                return name
        return "unknown"

    @staticmethod
    def _extract_chunk_content(chunk: ChatChunk) -> str:
        if not chunk or not getattr(chunk, "choices", None):
            return ""
        contents: List[str] = []
        for choice in chunk.choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    contents.append(content)
        return "".join(contents)

    def _estimate_tokens(self, messages: List[ChatMessage]) -> int:
        total_chars = 0
        for msg in messages:
            content = self._get_message_content(msg)
            total_chars += len(str(content))
        return total_chars // 4

    @staticmethod
    def _get_message_content(message: Any) -> Any:
        if isinstance(message, ChatMessage):
            return message.content
        if isinstance(message, dict):
            return message.get("content")
        return message

    def _message_has_images(self, message: Any) -> bool:
        content = self._get_message_content(message)
        if not isinstance(content, list):
            return False
        return any(isinstance(item, dict) and item.get("type") == "image_url" for item in content)

    async def _update_metrics(
        self,
        provider_name: str,
        latency: int,
        response: Optional[ApiResponse] = None,
        error: Optional[Exception] = None,
    ) -> None:
        async with self.metrics_lock:
            metrics = self.metrics.get(provider_name) or ProviderMetrics()
            metrics.request_count += 1
            if error:
                metrics.error_count += 1
            else:
                metrics.success_count += 1
            metrics.total_latency += latency
            metrics.average_latency = metrics.total_latency / max(1, metrics.request_count)
            if response and getattr(response, "usage", None):
                provider = self.providers.get(provider_name)
                if provider and hasattr(provider, "calculate_cost"):
                    metrics.total_cost += provider.calculate_cost(response.model, response.usage)
            self.metrics[provider_name] = metrics

    async def _cache_cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.cache_ttl // 2)
                current_time = time.monotonic()
                expired_keys = [
                    key
                    for key, (_, timestamp) in self.model_cache.items()
                    if current_time - timestamp > self.cache_ttl
                ]
                for key in expired_keys:
                    del self.model_cache[key]
                    logging.debug("Cleaned up expired cache for provider: %s", key)
            except asyncio.CancelledError:
                break
            except Exception as error:
                logging.error(
                    "Error in cache cleanup loop: %s", error, exc_info=True
                )
                await asyncio.sleep(60)

    async def shutdown(self) -> None:
        if self._cache_cleanup_task:
            self._cache_cleanup_task.cancel()
            try:
                await self._cache_cleanup_task
            except asyncio.CancelledError:
                pass
            except Exception as error:
                logging.error(
                    "Error during cache cleanup task shutdown: %s",
                    error,
                    exc_info=True,
                )

    def _is_acceptable(self, candidate: CandidateProvider, context: ProviderRequest) -> bool:
        if self.config.cost_threshold and candidate.estimated_cost > self.config.cost_threshold:
            return False
        if (
            context.priority == "high"
            and candidate.estimated_latency > self.config.high_priority_latency_threshold
        ):
            return False
        return True
