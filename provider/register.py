from .entities import ProviderMetaData, ProviderType
from .func_tool_manager import FuncCall


provider_registry: list[ProviderMetaData] = []
provider_cls_map: dict[str, ProviderMetaData] = {}

llm_tools = FuncCall()


def register_provider_adapter(
    provider_type_name: str,
    desc: str,
    provider_type: ProviderType = ProviderType.CHAT_COMPLETION,
    default_config_tmpl: dict | None = None,
    provider_display_name: str | None = None,
):
    """Decorator to register provider adapters."""

    def decorator(cls):
        if provider_type_name in provider_cls_map:
            raise ValueError(
                f"Provider adapter {provider_type_name} already registered."
            )

        if default_config_tmpl:
            if "type" not in default_config_tmpl:
                default_config_tmpl["type"] = provider_type_name
            if "enable" not in default_config_tmpl:
                default_config_tmpl["enable"] = False
            if "id" not in default_config_tmpl:
                default_config_tmpl["id"] = provider_type_name

        meta = ProviderMetaData(
            id="default",
            model=None,
            type=provider_type_name,
            desc=desc,
            provider_type=provider_type,
            cls_type=cls,
            default_config_tmpl=default_config_tmpl,
            provider_display_name=provider_display_name,
        )
        provider_registry.append(meta)
        provider_cls_map[provider_type_name] = meta
        return cls

    return decorator
