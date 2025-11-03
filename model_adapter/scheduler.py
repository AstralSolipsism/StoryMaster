import time
import asyncio
import random
from typing import Dict, List, Optional, AsyncIterable, Tuple, Any
from dataclasses import dataclass, field

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
                    if not ModelAdapterFactory._registry[provider_name].is_local:
                        await adapter.get_models()
                    self.adapters[provider_name] = adapter
                    print(f"Initialized adapter for provider: {provider_name}")
                else:
                    print(f"Failed to initialize {provider_name}: {validation.errors}")
            except Exception as error:
                print(f"Error initializing {provider_name}: {error}")
    
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
            self._update_metrics(schedule.provider, latency, response)
            return response
        except Exception as error:
            latency = int((time.monotonic() - start_time) * 1000)
            self._update_metrics(schedule.provider, latency, error=error)
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
            self._update_metrics(schedule.provider, latency)
        except Exception as error:
            latency = int((time.monotonic() - start_time) * 1000)
            self._update_metrics(schedule.provider, latency, error=error)
            async for chunk in self._handle_stream_failure(error, context, schedule):
                yield chunk
    
    async def _find_candidates(self, context: RequestContext) -> List[CandidateAdapter]:
        """查找候选适配器"""
        candidates = []
        
        for provider_name, adapter in self.adapters.items():
            try:
                models = await adapter.get_models()
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
                print(f"Failed to get models from {provider_name}: {error}")
        
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
        print(f"Request failed with {schedule.provider} ({schedule.model}): {error}")
        if self.config.fallback_providers:
            for fallback_provider in self.config.fallback_providers:
                if fallback_provider == schedule.provider:
                    continue
                
                adapter = self.adapters.get(fallback_provider)
                if not adapter:
                    continue

                try:
                    print(f"Attempting fallback to provider: {fallback_provider}")
                    # Create a new context for the fallback, removing the specific model
                    fallback_context = dataclasses.replace(context, model=None)
                    fallback_schedule = await self.schedule(fallback_context)
                    
                    print(f"Fallback using {fallback_provider} with model {fallback_schedule.model}")
                    params = self._build_request_params(context, fallback_schedule.model)
                    return await fallback_schedule.adapter.chat(params)
                except Exception as fallback_error:
                    print(f"Fallback provider {fallback_provider} also failed: {fallback_error}")
        
        raise error
    
    async def _handle_stream_failure(
        self, 
        error: Exception, 
        context: RequestContext, 
        schedule: ScheduleResult
    ) -> AsyncIterable[ChatChunk]:
        """处理流式请求失败"""
        print(f"Stream failed with {schedule.provider} ({schedule.model}): {error}")
        try:
            fallback_response = await self._handle_failure(error, context, schedule)
            
            # Convert the full response to a stream of chunks
            content = fallback_response.choices[0].message.content if fallback_response.choices else ''
            yield ChatChunk(
                id=fallback_response.id,
                object='chat.completion.chunk',
                created=fallback_response.created,
                model=fallback_response.model,
                choices=[{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]
            )
            yield ChatChunk(
                id=fallback_response.id,
                object='chat.completion.chunk',
                created=fallback_response.created,
                model=fallback_response.model,
                choices=[{'index': 0, 'delta': {}, 'finish_reason': fallback_response.choices[0].finish_reason}]
            )
        except Exception as fallback_error:
            yield ChatChunk(
                id=f"error-{int(time.time())}",
                object='chat.completion.chunk',
                created=int(time.time()),
                model=schedule.model,
                choices=[{
                    'index': 0,
                    'delta': {'content': f"\n\n--- ERROR ---\nInitial error: {error}\nFallback error: {fallback_error}"},
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
        # Simple token estimation, a real implementation should use a tokenizer
        prompt_tokens = sum(len(str(msg.content)) // 4 for msg in context.messages)
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
        
        defaults = {'anthropic': 2000, 'openrouter': 3000, 'ollama': 5000}
        return defaults.get(provider_name, 3000)
    
    def _build_request_params(self, context: RequestContext, model: str) -> Dict[str, Any]:
        """构建请求参数"""
        return {
            'messages': [msg.__dict__ for msg in context.messages],
            'model': model,
            'max_tokens': context.max_tokens,
            'temperature': context.temperature,
            'stream': context.stream,
            'tools': context.tools,
            'tool_choice': context.tool_choice,
            'system': context.system,
            'reasoning_budget': context.reasoning_budget,
        }
    
    def _is_acceptable(self, candidate: CandidateAdapter, context: RequestContext) -> bool:
        """检查候选是否可接受"""
        if self.config.cost_threshold and candidate.estimated_cost > self.config.cost_threshold:
            return False
        if context.priority == 'high' and candidate.estimated_latency > 5000:
            return False
        return True
    
    def _update_metrics(self, provider_name: str, latency: int, response: Optional[ApiResponse] = None, error: Optional[Exception] = None) -> None:
        """更新指标"""
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