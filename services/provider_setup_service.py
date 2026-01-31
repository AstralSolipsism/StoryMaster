from typing import Any, Dict, List, Optional

from ..provider import ProviderManager, ProviderProfile, ProviderProfileManager
from ..provider.register import provider_cls_map
from ..provider.entities import ModelInfo


class ProviderSetupService:
    def __init__(
        self,
        provider_manager: ProviderManager,
        profile_manager: ProviderProfileManager,
    ) -> None:
        self.provider_manager = provider_manager
        self.profile_manager = profile_manager

    def get_provider_requirements(self) -> List[Dict[str, Any]]:
        return self.profile_manager.get_provider_requirements()

    async def list_models_with_scores(
        self,
        provider_type: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        priority: str = "medium",
    ) -> List[Dict[str, Any]]:
        provider_class = provider_cls_map.get(provider_type)
        if not provider_class:
            raise ValueError(f"Unknown provider type: {provider_type}")

        config = self.profile_manager.build_provider_config_from_inputs(
            provider_type=provider_type,
            api_key=api_key,
            base_url=base_url,
            headers=headers,
            extra_config=extra_config,
        )

        provider = provider_class.cls_type(config, {})
        models = await provider.get_models()
        return self._score_models(provider_type, provider, models, priority)

    def save_profile(
        self,
        profile_id: str,
        name: str,
        provider_type: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        extra_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        profile = ProviderProfile(
            profile_id=profile_id,
            name=name,
            provider_type=provider_type,
            api_key=api_key,
            base_url=base_url,
            model=model,
            headers=headers or {},
            extra_config=extra_config or {},
        )
        return self.profile_manager.save_profile(profile)

    async def activate_profile(self, profile_id: str) -> None:
        self.profile_manager.set_active_profile(profile_id)
        profile = self.profile_manager.load_profile(profile_id)
        provider_configs = self.profile_manager.build_provider_config(profile)
        await self.provider_manager.shutdown()
        self.provider_manager.provider_configs = provider_configs
        self.provider_manager.config.default_provider = profile.provider_type
        self.provider_manager.providers = {}
        self.provider_manager.metrics = {}
        self.provider_manager.model_cache = {}
        await self.provider_manager.initialize()

    def list_profiles(self) -> List[ProviderProfile]:
        return self.profile_manager.list_profiles()

    def _score_models(
        self,
        provider_type: str,
        provider,
        models: List[ModelInfo],
        priority: str,
    ) -> List[Dict[str, Any]]:
        scored = []
        for model in models:
            cost = 0.0
            if hasattr(provider, "calculate_cost") and model.pricing:
                cost = model.pricing.input_price or 0.0
            latency = self.provider_manager.get_estimated_latency(provider_type)
            score = self.provider_manager.calculate_score(cost, latency, priority=priority)
            scored.append(
                {
                    "id": model.id,
                    "name": model.name,
                    "context_window": model.context_window,
                    "max_tokens": model.max_tokens,
                    "supports_images": model.capabilities.supports_images
                    if model.capabilities
                    else None,
                    "supports_prompt_cache": model.capabilities.supports_prompt_cache
                    if model.capabilities
                    else None,
                    "supports_reasoning_budget": model.capabilities.supports_reasoning_budget
                    if model.capabilities
                    else None,
                    "input_price": model.pricing.input_price if model.pricing else None,
                    "output_price": model.pricing.output_price if model.pricing else None,
                    "score": score,
                    "estimated_latency": latency,
                }
            )
        return scored
