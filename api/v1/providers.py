from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from ...models.provider_setup_models import (
    ProviderRequirement,
    ProviderModelInfo,
    ProviderModelListRequest,
    ProviderModelListResponse,
    ProviderProfilePayload,
    ProviderProfileResponse,
    ProviderProfileActivateRequest,
)
from ...services.provider_setup_service import ProviderSetupService


router = APIRouter(prefix="/providers", tags=["providers"])


def get_provider_setup_service(request: Request) -> ProviderSetupService:
    provider_manager = getattr(request.app.state, "provider_manager", None)
    profile_manager = getattr(request.app.state, "provider_profile_manager", None)
    if not provider_manager or not profile_manager:
        raise HTTPException(status_code=500, detail="Provider service not initialized")
    return ProviderSetupService(provider_manager, profile_manager)


@router.get("/requirements", response_model=List[ProviderRequirement])
async def get_provider_requirements(
    service: ProviderSetupService = Depends(get_provider_setup_service),
) -> List[ProviderRequirement]:
    return service.get_provider_requirements()


@router.post("/models", response_model=ProviderModelListResponse)
async def list_provider_models(
    request: ProviderModelListRequest,
    service: ProviderSetupService = Depends(get_provider_setup_service),
) -> ProviderModelListResponse:
    try:
        models = await service.list_models_with_scores(
            provider_type=request.provider_type,
            api_key=request.api_key,
            base_url=request.base_url,
            headers=request.headers,
            extra_config=request.extra_config,
            priority=request.priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ProviderModelListResponse(
        provider_type=request.provider_type,
        models=[ProviderModelInfo(**model) for model in models],
    )


@router.post("/profiles", response_model=ProviderProfileResponse)
async def save_provider_profile(
    request: ProviderProfilePayload,
    service: ProviderSetupService = Depends(get_provider_setup_service),
) -> ProviderProfileResponse:
    try:
        profile_id = service.save_profile(
            profile_id=request.profile_id,
            name=request.name,
            provider_type=request.provider_type,
            model=request.model,
            api_key=request.api_key,
            base_url=request.base_url,
            headers=request.headers,
            extra_config=request.extra_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ProviderProfileResponse(
        profile_id=profile_id,
        name=request.name,
        provider_type=request.provider_type,
        model=request.model,
    )


@router.post("/profiles/activate")
async def activate_provider_profile(
    request: ProviderProfileActivateRequest,
    service: ProviderSetupService = Depends(get_provider_setup_service),
) -> Dict[str, Any]:
    try:
        await service.activate_profile(request.profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "profile_id": request.profile_id}


@router.get("/profiles", response_model=List[ProviderProfileResponse])
async def list_provider_profiles(
    service: ProviderSetupService = Depends(get_provider_setup_service),
) -> List[ProviderProfileResponse]:
    profiles = service.list_profiles()
    return [
        ProviderProfileResponse(
            profile_id=profile.profile_id,
            name=profile.name,
            provider_type=profile.provider_type,
            model=profile.model or "",
        )
        for profile in profiles
    ]
