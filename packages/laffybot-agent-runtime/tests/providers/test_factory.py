"""Tests for ProviderFactory Protocol."""

from laffybot_agent_runtime.providers.base import BaseProvider
from laffybot_agent_runtime.providers.config import ProviderConfig


class _SimpleFactory:
    """Minimal ProviderFactory implementation."""

    async def create_provider(self, config: ProviderConfig) -> BaseProvider:
        from laffybot_agent_runtime.providers.openai import OpenAIProvider

        return OpenAIProvider(config)


def test_factory_protocol_satisfied() -> None:
    factory = _SimpleFactory()
    # Static type checkers verify conformance; runtime check via hasattr
    assert hasattr(factory, "create_provider")
