import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .entities import ProviderConfig, ValidationResult
from .register import provider_cls_map


MAX_PROFILE_ID_LENGTH = 50


@dataclass
class ProviderProfile:
    profile_id: str
    name: str
    provider_type: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    extra_config: Dict[str, Any] = field(default_factory=dict)


class ProviderProfileManager:
    def __init__(self, storage_path: Optional[str] = None) -> None:
        default_path = Path(__file__).resolve().parent.parent / "configs" / "provider_profiles"
        self.storage_path = Path(storage_path) if storage_path else default_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.active_profile_file = self.storage_path / "active_profile.json"

    def list_profiles(self) -> List[ProviderProfile]:
        profiles: List[ProviderProfile] = []
        for profile_file in self.storage_path.glob("*.json"):
            if profile_file.name == "active_profile.json":
                continue
            try:
                profiles.append(self.load_profile(profile_file.stem))
            except Exception:
                continue
        return profiles

    def load_profile(self, profile_id: str) -> ProviderProfile:
        self._validate_profile_id(profile_id)
        profile_file = self.storage_path / f"{profile_id}.json"
        if not profile_file.exists():
            raise ValueError(f"Profile {profile_id} does not exist")
        data = json.loads(profile_file.read_text(encoding="utf-8"))
        return self._dict_to_profile(data)

    def save_profile(self, profile: ProviderProfile) -> str:
        validation = self.validate_profile(profile)
        if not validation.is_valid:
            raise ValueError(f"Profile validation failed: {validation.errors}")
        profile_file = self.storage_path / f"{profile.profile_id}.json"
        profile_file.write_text(
            json.dumps(self._profile_to_dict(profile), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return profile.profile_id

    def delete_profile(self, profile_id: str) -> None:
        self._validate_profile_id(profile_id)
        profile_file = self.storage_path / f"{profile_id}.json"
        if profile_file.exists():
            profile_file.unlink()
        if self.active_profile_file.exists():
            active = json.loads(self.active_profile_file.read_text(encoding="utf-8"))
            if active.get("profile_id") == profile_id:
                self.active_profile_file.unlink()

    def set_active_profile(self, profile_id: str) -> None:
        profile = self.load_profile(profile_id)
        payload = {"profile_id": profile.profile_id}
        self.active_profile_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_active_profile(self) -> Optional[ProviderProfile]:
        if not self.active_profile_file.exists():
            return None
        data = json.loads(self.active_profile_file.read_text(encoding="utf-8"))
        profile_id = data.get("profile_id")
        if not profile_id:
            return None
        return self.load_profile(profile_id)

    def validate_profile(self, profile: ProviderProfile) -> ValidationResult:
        errors: List[str] = []
        try:
            self._validate_profile_id(profile.profile_id)
        except ValueError as exc:
            errors.append(str(exc))

        if not profile.name:
            errors.append("Profile name is required")

        if not profile.provider_type:
            errors.append("Provider type is required")
        elif profile.provider_type not in provider_cls_map:
            errors.append(f"Unknown provider type: {profile.provider_type}")

        if not profile.model:
            errors.append("Model is required")

        if profile.provider_type in {
            "openai_chat_completion",
            "openai_compatible_chat_completion",
            "groq_chat_completion",
            "zhipu_chat_completion",
            "openrouter_chat_completion",
            "anthropic_chat_completion",
        } and not profile.api_key:
            errors.append("API key is required for this provider")

        if profile.provider_type in {"openai_compatible_chat_completion"} and not profile.base_url:
            errors.append("Base URL is required for openai compatible provider")

        if profile.provider_type in {
            "ollama_chat_completion",
            "openai_chat_completion",
            "groq_chat_completion",
            "zhipu_chat_completion",
            "openrouter_chat_completion",
            "anthropic_chat_completion",
        } and profile.base_url:
            errors.append("Base URL is not supported for this provider")

        if profile.provider_type in {"ollama_chat_completion"} and not profile.base_url:
            errors.append("Base URL is required for ollama provider")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def build_provider_config(self, profile: ProviderProfile) -> Dict[str, ProviderConfig]:
        provider_type = profile.provider_type
        config: ProviderConfig = {"timeout": 30, "max_retries": 3}

        if provider_type == "openai_chat_completion":
            config.update({"api_key": profile.api_key})
        elif provider_type == "openai_compatible_chat_completion":
            config.update(
                {
                    "api_key": profile.api_key,
                    "openai_compatible_base_url": profile.base_url,
                }
            )
        elif provider_type == "groq_chat_completion":
            config.update({"api_key": profile.api_key})
        elif provider_type == "zhipu_chat_completion":
            config.update({"api_key": profile.api_key})
        elif provider_type == "openrouter_chat_completion":
            config.update({"api_key": profile.api_key})
        elif provider_type == "anthropic_chat_completion":
            config.update({"api_key": profile.api_key})
        elif provider_type == "ollama_chat_completion":
            config.update(
                {
                    "ollama_base_url": profile.base_url,
                    "timeout": 60,
                    "max_retries": 1,
                }
            )

        config["model"] = profile.model

        if profile.headers:
            config["openai_headers"] = profile.headers

        if profile.extra_config:
            config.update(profile.extra_config)

        return {provider_type: config}

    def build_provider_config_from_inputs(
        self,
        provider_type: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        extra_config: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> ProviderConfig:
        config: ProviderConfig = {"timeout": 30, "max_retries": 3}

        if provider_type == "openai_chat_completion":
            config.update({"api_key": api_key})
        elif provider_type == "openai_compatible_chat_completion":
            config.update(
                {
                    "api_key": api_key,
                    "openai_compatible_base_url": base_url,
                }
            )
        elif provider_type == "groq_chat_completion":
            config.update({"api_key": api_key})
        elif provider_type == "zhipu_chat_completion":
            config.update({"api_key": api_key})
        elif provider_type == "openrouter_chat_completion":
            config.update({"api_key": api_key})
        elif provider_type == "anthropic_chat_completion":
            config.update({"api_key": api_key})
        elif provider_type == "ollama_chat_completion":
            config.update(
                {
                    "ollama_base_url": base_url,
                    "timeout": 60,
                    "max_retries": 1,
                }
            )

        if model:
            config["model"] = model

        if headers:
            config["openai_headers"] = headers

        if extra_config:
            config.update(extra_config)

        return config

    def get_provider_requirements(self) -> List[Dict[str, Any]]:
        providers = []
        for provider_type, meta in provider_cls_map.items():
            requirements = {
                "provider_type": provider_type,
                "provider_display_name": meta.provider_display_name or meta.desc or provider_type,
                "required_fields": ["model"],
                "optional_fields": [],
            }
            if provider_type in {
                "openai_chat_completion",
                "openai_compatible_chat_completion",
                "groq_chat_completion",
                "zhipu_chat_completion",
                "openrouter_chat_completion",
                "anthropic_chat_completion",
            }:
                requirements["required_fields"].append("api_key")
            if provider_type in {"openai_compatible_chat_completion", "ollama_chat_completion"}:
                requirements["required_fields"].append("base_url")
            if provider_type in {
                "openai_chat_completion",
                "openai_compatible_chat_completion",
                "groq_chat_completion",
                "zhipu_chat_completion",
            }:
                requirements["optional_fields"].append("headers")
            requirements["optional_fields"].append("extra_config")
            providers.append(requirements)
        return providers

    def _profile_to_dict(self, profile: ProviderProfile) -> Dict[str, Any]:
        return asdict(profile)

    def _dict_to_profile(self, data: Dict[str, Any]) -> ProviderProfile:
        return ProviderProfile(
            profile_id=data.get("profile_id", ""),
            name=data.get("name", ""),
            provider_type=data.get("provider_type", ""),
            api_key=data.get("api_key"),
            base_url=data.get("base_url"),
            model=data.get("model"),
            headers=data.get("headers") or {},
            extra_config=data.get("extra_config") or {},
        )

    def _validate_profile_id(self, profile_id: str) -> None:
        if not profile_id:
            raise ValueError("Profile ID is required")
        pattern = r"^[a-zA-Z0-9_-]+$"
        if not re.match(pattern, profile_id):
            raise ValueError("Profile ID contains invalid characters")
        if len(profile_id) > MAX_PROFILE_ID_LENGTH:
            raise ValueError("Profile ID is too long")
