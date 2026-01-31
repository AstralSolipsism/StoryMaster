from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProviderRequirement(BaseModel):
    provider_type: str
    provider_display_name: str
    required_fields: List[str]
    optional_fields: List[str]


class ProviderModelInfo(BaseModel):
    id: str
    name: Optional[str] = None
    context_window: Optional[int] = None
    max_tokens: Optional[int] = None
    supports_images: Optional[bool] = None
    supports_prompt_cache: Optional[bool] = None
    supports_reasoning_budget: Optional[bool] = None
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    score: Optional[float] = None
    estimated_latency: Optional[int] = None


class ProviderModelListRequest(BaseModel):
    provider_type: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    extra_config: Optional[Dict[str, Any]] = None
    priority: str = "medium"


class ProviderModelListResponse(BaseModel):
    provider_type: str
    models: List[ProviderModelInfo]


class ProviderProfilePayload(BaseModel):
    profile_id: str
    name: str
    provider_type: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    extra_config: Optional[Dict[str, Any]] = None


class ProviderProfileResponse(BaseModel):
    profile_id: str
    name: str
    provider_type: str
    model: str


class ProviderProfileActivateRequest(BaseModel):
    profile_id: str = Field(..., min_length=1)
