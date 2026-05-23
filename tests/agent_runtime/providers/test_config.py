"""Tests for ProviderConfig dataclass."""

from laffybot.agent_runtime.providers.config import ProviderConfig


class TestProviderConfig:
    def test_default_extra_headers(self) -> None:
        cfg = ProviderConfig(
            provider_id="p1", name="test", api_key="key", base_url="http://test"
        )
        assert cfg.extra_headers == {}

    def test_extra_body(self) -> None:
        cfg = ProviderConfig(
            provider_id="p1",
            name="test",
            api_key="key",
            base_url="http://test",
            extra_body={"custom": "value"},
        )
        assert cfg.extra_body == {"custom": "value"}
