"""Provider factory — selects Provider implementation by provider type.

Architecture note: The PROVIDER_MAP is injected from the composition root
(dependencies.py) so the service layer has no compile-time dependency on
specific Provider SDKs.
"""

from __future__ import annotations

from laffybot_agent_runtime.providers.base import BaseProvider
from laffybot_agent_runtime.providers.config import (
    ProviderConfig as AgentProviderConfig,
)

from laffybot.db.provider_store import ProviderConfig as DbProviderConfig
from laffybot.service.protocols import ProviderFactory as _ProviderFactoryProtocol

ProviderFactory = _ProviderFactoryProtocol


def to_runtime_config(config: DbProviderConfig) -> AgentProviderConfig:
    return AgentProviderConfig(
        provider_id=config.provider_id,
        name=config.name,
        api_key=config.api_key,
        base_url=config.base_url,
        extra_headers=config.extra_headers or {},
        extra_body=config.extra_body or {},
    )


class DefaultProviderFactory(ProviderFactory):
    """Provider factory with injectable provider class map.

    The provider_map is a dict of provider_type → provider_class.
    Registration happens in the composition root (dependencies.py)
    so the service layer doesn't depend on specific SDKs.
    """

    def __init__(
        self,
        provider_map: dict[str, type[BaseProvider]] | None = None,
    ) -> None:
        self._provider_map = provider_map or {}

    async def create_provider(self, config: DbProviderConfig) -> BaseProvider:
        runtime_config = to_runtime_config(config)
        provider_type = self._detect_provider_type(config)
        provider_cls = self._provider_map.get(provider_type)
        if provider_cls is None:
            raise ValueError(
                f"Unknown provider type: {provider_type!r}. "
                f"Available: {list(self._provider_map)}"
            )
        return provider_cls(runtime_config)

    @staticmethod
    def _detect_provider_type(config: DbProviderConfig) -> str:
        """Detect provider type from config.

        Currently always returns 'openai'.  In the future this could
        inspect base_url, support Anthropic, etc.
        """
        return "openai"
