import time
import asyncio
import random
import logging
from typing import Dict, List, Optional, AsyncIterable, Tuple, Any
from dataclasses import dataclass, field
import dataclasses

from .interfaces import (
    IModelAdapter,
    ChatMessage,
    ApiResponse,
    ChatChunk,
    ModelInfo,
    TokenUsage,
    ProviderConfig,
)
from .factory import ModelAdapterFactory

@dataclass
class SchedulerConfig:
    """调度器配置"""
    default_provider: str
    fallback_providers: Optional[List[str]] = None
    max_retries: int = 3
    retry_delay: int = 1  # in seconds
    enable_load_balancing: bool = False
    cost_threshold: Optional[float] = None
    high_priority_latency_threshold: int = 5000
    # 将硬编码的默认值提取为类常量
    DEFAULT_LATENCIES: Dict[str, int] = field(default_factory=lambda: {'anthropic': 2000, 'openrouter': 3000, 'ollama': 500})

@dataclass
class RequestContext:
    """请求上下文"""
    messages: List[ChatMessage]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    priority: str = 'medium'  # 'low' | 'medium' | 'high'
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    # Adding other potential params from doc
    tools: Optional[List[Any]] = None
    tool_choice: Optional[Any] = None
    system: Optional[str] = None
    reasoning_budget: Optional[int] = None


@dataclass
class ScheduleResult:
    """调度结果"""
    adapter: IModelAdapter
    model: str
    provider: str
    estimated_cost: float
    estimated_latency: int

@dataclass
class CandidateAdapter:
    """候选适配器"""
    adapter: IModelAdapter
    provider: str
    model: str
    estimated_cost: float
    estimated_latency: int
    score: float

@dataclass
class ProviderMetrics:
    """提供商指标"""
    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_latency: int = 0
    average_latency: float = 0.0
    total_cost: float = 0.0

class ModelScheduler:
    """统一模型调度器"""
    
    def __init__(self, config: SchedulerConfig, provider_configs: Dict[str, ProviderConfig] = None):
        self.config = config
        self.provider_configs = provider_configs or {}
        self.adapters: Dict[str, IModelAdapter] = {}
        self.metrics: Dict[str, ProviderMetrics] = {}
        self.model_cache: Dict[str, Tuple[List[ModelInfo], float]] = {}
        self.cache_ttl: int = 600  # 10 minutes
        # 缓存清理任务
        self._cache_cleanup_task: Optional[asyncio.Task] = None
        self.metrics_lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """初始化适配器"""
        providers = ModelAdapterFactory.get_registered_providers()
        
        for provider_name in providers:
            try:
                config = self._get_provider_config(provider_name)
                adapter = ModelAdapterFactory.create_adapter(provider_name, config)
                
                validation = adapter.validate_config(config)
                if validation.is_valid:
                    # Pre-load models for non-local providers
                    adapter_info = ModelAdapterFactory.get_adapter_info(provider_name)
                    if adapter_info and not adapter_info.is_local:
                        await adapter.get_models()
                    self.adapters[provider_name] = adapter
                    logging.info("Initialized adapter for provider: %s", provider_name)
                else:
                    logging.warning("Failed to initialize %s: %s", provider_name, validation.errors)
            except Exception as error:
                logging.error("Error initializing provider %s", provider_name, exc_info=True)
        
        # 启动缓存清理任务
        self._cache_cleanup_task = asyncio.create_task(self._cache_cleanup_loop())
    
    async def schedule(self, context: RequestContext) -> ScheduleResult:
        """调度最佳适配器"""
        candidates = await self._find_candidates(context)
        if not candidates:
            raise ValueError('No suitable adapters or models found for the request.')
        
        best = self._select_best_candidate(candidates, context)
        
        return ScheduleResult(
            adapter=best.adapter,
            model=best.model,
            provider=best.provider,
            estimated_cost=best.estimated_cost,
            estimated_latency=best.estimated_latency
        )
    
    async def chat(self, context: RequestContext) -> ApiResponse:
        """执行聊天请求"""
        schedule = await self.schedule(context)
        
        start_time = time.monotonic()
        try:
            response = await self._execute_with_retry(
                schedule.adapter,
                'chat',
                self._build_request_params(context, schedule.model)
            )
            
            latency = int((time.monotonic() - start_time) * 1000)
            await self._update_metrics(schedule.provider, latency, response)
            return response
        except Exception as error:
            latency = int((time.monotonic() - start_time) * 1000)
            await self._update_metrics(schedule.provider, latency, error=error)
            return await self._handle_failure(error, context, schedule)
    
    async def chat_stream(self, context: RequestContext) -> AsyncIterable[ChatChunk]:
        """执行流式聊天请求"""
        schedule = await self.schedule(context)
        start_time = time.monotonic()
        
        try:
            stream = await self._execute_with_retry(
                schedule.adapter,
                'chat_stream',
                self._build_request_params(context, schedule.model)
            )
            async for chunk in stream:
                yield chunk
            
            latency = int((time.monotonic() - start_time) * 1000)
            await self._update_metrics(schedule.provider, latency)
        except Exception as error:
            latency = int((time.monotonic() - start_time) * 1000)
            await self._update_metrics(schedule.provider, latency, error=error)
            async for chunk in self._handle_stream_failure(error, context, schedule):
                yield chunk
    
    async def _find_candidates(self, context: RequestContext) -> List[CandidateAdapter]:
        """查找候选适配器"""
        candidates = []
        
        for provider_name, adapter in self.adapters.items():
            try:
                cached_models, timestamp = self.model_cache.get(provider_name, (None, 0))
                if cached_models and time.monotonic() - timestamp < self.cache_ttl:
                    models = cached_models
                else:
                    models = await adapter.get_models()
                    self.model_cache[provider_name] = (models, time.monotonic())
                suitable_models = self._find_suitable_models(models, context)
                
                for model in suitable_models:
                    # If a specific model is requested, only consider that one
                    if context.model and model.id != context.model:
                        continue

                    estimated_cost = self._estimate_cost(adapter, model.id, context)
                    estimated_latency = self._estimate_latency(provider_name)
                    
                    candidates.append(CandidateAdapter(
                        adapter=adapter,
                        provider=provider_name,
                        model=model.id,
                        estimated_cost=estimated_cost,
                        estimated_latency=estimated_latency,
                        score=self._calculate_score(estimated_cost, estimated_latency, context)
                    ))
            except Exception as error:
                logging.warning("Failed to get models from %s: %s", provider_name, error)
        
        return sorted(candidates, key=lambda x: x.score, reverse=True)
    
    def _select_best_candidate(
        self, 
        candidates: List[CandidateAdapter], 
        context: RequestContext
    ) -> CandidateAdapter:
        """选择最佳候选"""
        # If a specific model was requested, find the best candidate for it
        if context.model:
            model_candidates = [c for c in candidates if c.model == context.model]
            if model_candidates:
                return model_candidates[0] # Return the highest-scored one

        # Prioritize default provider if it's acceptable
        default_candidate = next(
            (c for c in candidates if c.provider == self.config.default_provider), 
            None
        )
        if default_candidate and self._is_acceptable(default_candidate, context):
            return default_candidate
        
        # Fallback to the highest-scored candidate
        return candidates[0]
    
    def _calculate_score(
        self, 
        cost: float, 
        latency: int, 
        context: RequestContext
    ) -> float:
        """计算候选得分"""
        score = 100.0
        
        if self.config.cost_threshold and cost > self.config.cost_threshold:
            score -= 50.0
        else:
            score -= min(30.0, cost * 1000) # Scale cost penalty
        
        score -= min(20.0, latency / 200.0) # Scale latency penalty
        
        if context.priority == 'high':
            score += 20.0
        elif context.priority == 'medium':
            score += 10.0
        
        return max(0.0, score)
    
    async def _execute_with_retry(
        self, 
        adapter: IModelAdapter, 
        method: str, 
        params: Dict[str, Any]
    ) -> Any:
        """执行带重试的请求"""
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                if method == 'chat':
                    return await adapter.chat(params)
                elif method == 'chat_stream':
                    return await adapter.chat_stream(params)
                else:
                    raise ValueError(f"Unknown method: {method}")
            except Exception as error:
                last_error = error
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        
        raise last_error
    
    async def _handle_failure(
        self, 
        error: Exception, 
        context: RequestContext, 
        schedule: ScheduleResult
    ) -> ApiResponse:
        """处理请求失败"""
        logging.warning("Request failed with %s (%s): %s", schedule.provider, schedule.model, error)
        last_fallback_error = None
        if self.config.fallback_providers:
            for fallback_provider in self.config.fallback_providers:
                if fallback_provider == schedule.provider:
                    continue
                
                adapter = self.adapters.get(fallback_provider)
                if not adapter:
                    continue

                try:
                    logging.info("Attempting fallback to provider: %s", fallback_provider)
                    # Create a new context for the fallback, removing the specific model
                    fallback_context = dataclasses.replace(context, model=None)
                    
                    # Create a temporary scheduler config for fallback
                    fallback_config = dataclasses.replace(self.config, default_provider=fallback_provider)
                    
                    # Create a temporary scheduler to handle the fallback
                    fallback_scheduler = ModelScheduler(fallback_config, self.provider_configs)
                    fallback_scheduler.adapters = self.adapters # Reuse existing adapters
                    
                    fallback_schedule = await fallback_scheduler.schedule(fallback_context)
                    
                    logging.info("Fallback using %s with model %s", fallback_provider, fallback_schedule.model)
                    params = self._build_request_params(context, fallback_schedule.model)
                    return await fallback_schedule.adapter.chat(params)
                except Exception as fallback_error:
                    logging.warning("Fallback provider %s also failed: %s", fallback_provider, fallback_error)
                    last_fallback_error = fallback_error
        
        if last_fallback_error:
            raise last_fallback_error from error
        raise error
    
    async def _handle_stream_failure(
        self, 
        error: Exception, 
        context: RequestContext, 
        schedule: ScheduleResult
    ) -> AsyncIterable[ChatChunk]:
        """处理流式请求失败"""
        logging.warning("Stream failed with %s (%s): %s", schedule.provider, schedule.model, error)
        
        try:
            fallback_response = await self._handle_failure(error, context, schedule)
            
            if not fallback_response.choices:
                raise ValueError("No choices in fallback response")
            
            # 获取内容，确保不为None
            content = fallback_response.choices[0].message.content if fallback_response.choices[0].message else ''
            content = content or ''  # 确保不是None
            
            # 第一个chunk：发送内容
            yield ChatChunk(
                id=fallback_response.id,
                object='chat.completion.chunk',
                created=fallback_response.created,
                model=fallback_response.model,
                choices=[{
                    'index': 0,
                    'delta': {'content': content} if content else {},  # 空内容时使用空字典
                    'finish_reason': None
                }]
            )
            
            # 第二个chunk：发送结束标记
            yield ChatChunk(
                id=fallback_response.id,
                object='chat.completion.chunk',
                created=fallback_response.created,
                model=fallback_response.model,
                choices=[{
                    'index': 0,
                    'delta': {},  # 结束chunk使用空字典
                    'finish_reason': fallback_response.choices[0].finish_reason or 'stop'
                }]
            )
        
        except Exception as fallback_error:
            # 统一错误消息格式，确保包含"ERROR"（不带额外字符）
            error_message = "ERROR: An unexpected error occurred. Please try again."
            
            yield ChatChunk(
                id=f"error-{int(time.time())}",
                object='chat.completion.chunk',
                created=int(time.time()),
                model=schedule.model,
                choices=[{
                    'index': 0,
                    'delta': {'content': error_message},
                    'finish_reason': 'error'
                }]
            )

    
    def _get_provider_config(self, provider_name: str) -> ProviderConfig:
        """获取提供商配置"""
        return self.provider_configs.get(provider_name, ProviderConfig())
    
    def _find_suitable_models(self, models: List[ModelInfo], context: RequestContext) -> List[ModelInfo]:
        """查找合适的模型"""
        suitable = []
        has_images = any(
            isinstance(msg.content, list) and 
            any(item.get('type') == 'image_url' for item in msg.content)
            for msg in context.messages
        )
        
        for model in models:
            if model.deprecated:
                continue
            if has_images and not model.capabilities.supports_images:
                continue
            
            suitable.append(model)
        
        return suitable
    
    def _estimate_cost(self, adapter: IModelAdapter, model_id: str, context: RequestContext) -> float:
        """估算成本"""
        # 使用更准确的token估算方法
        prompt_tokens = self._estimate_tokens(context.messages)
        completion_tokens = context.max_tokens or 1000
        
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
        
        return adapter.calculate_cost(model_id, usage)
    
    def _estimate_latency(self, provider_name: str) -> int:
        """估算延迟"""
        metrics = self.metrics.get(provider_name)
        if metrics and metrics.average_latency > 0:
            return int(metrics.average_latency)
        
        return self.config.DEFAULT_LATENCIES.get(provider_name, 3000)
    
    def _build_request_params(self, context: RequestContext, model: str) -> Dict[str, Any]:
        """构建请求参数"""
        # 使用更安全的消息序列化方法
        messages = [self._serialize_message(msg) for msg in context.messages]
        return {
            'messages': messages,
            'model': model,
            'max_tokens': context.max_tokens,
            'temperature': context.temperature,
            'stream': context.stream,
            'tools': context.tools,
            'tool_choice': context.tool_choice,
            'system': context.system,
            'reasoning_budget': context.reasoning_budget,
        }
    
    def _estimate_tokens(self, messages: List[ChatMessage]) -> int:
        """估算token数量（使用更准确的方法）"""
        # 简单的token估算，实际应用中应该使用tiktoken等专业库
        total_chars = sum(len(str(msg.content)) for msg in messages)
        return total_chars // 4  # 粗略估算：1个token约等于4个字符
    
    def _serialize_message(self, message: ChatMessage) -> Dict[str, Any]:
        """安全地序列化消息对象"""
        # 使用dataclass.asdict或自定义序列化方法，避免直接使用__dict__
        if hasattr(message, '__dict__'):
            return message.__dict__
        else:
            # 对于dataclass对象，使用更安全的序列化方法
            return {
                'role': getattr(message, 'role', 'user'),
                'content': getattr(message, 'content', ''),
                'name': getattr(message, 'name', None)
            }
    
    async def _cache_cleanup_loop(self) -> None:
        """定期清理过期缓存"""
        while True:
            try:
                await asyncio.sleep(self.cache_ttl // 2)  # 每半个TTL时间检查一次
                current_time = time.monotonic()
                expired_keys = [
                    key for key, (_, timestamp) in self.model_cache.items()
                    if current_time - timestamp > self.cache_ttl
                ]
                for key in expired_keys:
                    del self.model_cache[key]
                    logging.debug("Cleaned up expired cache for provider: %s", key)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error("Error in cache cleanup loop: %s", e, exc_info=True)
                # 添加延迟避免快速重试导致CPU占用过高
                await asyncio.sleep(60)  # 等待60秒后重试

    
    async def shutdown(self) -> None:
        """关闭调度器，清理资源"""
        if self._cache_cleanup_task:
            self._cache_cleanup_task.cancel()
            try:
                await self._cache_cleanup_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logging.error("Error during cache cleanup task shutdown: %s", e, exc_info=True)
    
    def _is_acceptable(self, candidate: CandidateAdapter, context: RequestContext) -> bool:
        """检查候选是否可接受"""
        if self.config.cost_threshold and candidate.estimated_cost > self.config.cost_threshold:
            return False
        if context.priority == 'high' and candidate.estimated_latency > self.config.high_priority_latency_threshold:
            return False
        return True
    
    async def _update_metrics(self, provider_name: str, latency: int, response: Optional[ApiResponse] = None, error: Optional[Exception] = None) -> None:
        """更新指标"""
        async with self.metrics_lock:
            metrics = self.metrics.get(provider_name, ProviderMetrics())
            metrics.request_count += 1
            metrics.total_latency += latency
            
            if error:
                metrics.error_count += 1
            else:
                metrics.success_count += 1
                if response and response.usage:
                    cost = self.adapters[provider_name].calculate_cost(response.model, response.usage)
                    metrics.total_cost += cost

            metrics.average_latency = metrics.total_latency / metrics.request_count
            self.metrics[provider_name] = metrics