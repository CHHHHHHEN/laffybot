"""Tests for provider error hierarchy."""

from laffybot.agent_runtime.providers.errors import (
    ModelNameConflictError,
    ModelNotFoundError,
    NoActiveProviderError,
    ProviderConfigError,
    ProviderConnectionError,
    ProviderError,
    ProviderNotFoundError,
)


class TestProviderError:
    def test_is_exception(self) -> None:
        assert issubclass(ProviderError, Exception)

    def test_provider_not_found_message(self) -> None:
        err = ProviderNotFoundError("p1")
        assert "p1" in str(err)

    def test_model_not_found_message(self) -> None:
        err = ModelNotFoundError("gpt-4")
        assert "gpt-4" in str(err)

    def test_no_active_provider_message(self) -> None:
        err = NoActiveProviderError()
        assert "No active provider" in str(err)

    def test_model_name_conflict_message(self) -> None:
        err = ModelNameConflictError("gpt-4", "p1")
        assert "gpt-4" in str(err)
        assert "p1" in str(err)

    def test_config_error(self) -> None:
        assert issubclass(ProviderConfigError, ProviderError)

    def test_connection_error(self) -> None:
        assert issubclass(ProviderConnectionError, ProviderError)
