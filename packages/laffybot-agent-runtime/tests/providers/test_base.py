"""Tests for BaseProvider abstract interface."""

from laffybot_agent_runtime.providers.base import BaseProvider
from laffybot_agent_runtime.providers.config import ProviderConfig


def test_can_instantiate_with_config() -> None:
    cfg = ProviderConfig(
        provider_id="p1", name="test", api_key="k", base_url="http://t"
    )

    class _Concrete(BaseProvider):
        async def chat_completion(self, **kwargs):
            from laffybot_agent_runtime.providers.types import SuccessLLMResponse

            return SuccessLLMResponse(content="ok")

        async def chat_completion_stream(self, **kwargs):
            from laffybot_agent_runtime.providers.types import SuccessLLMResponse

            return SuccessLLMResponse(content="")

    p = _Concrete(cfg)
    assert p.config is cfg
