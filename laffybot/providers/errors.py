"""Domain exceptions for provider management."""

from __future__ import annotations


class ProviderError(Exception):
    """Base exception for all provider-related errors."""


class ProviderNotFoundError(ProviderError):
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"Provider '{provider_id}' not found")


class ProviderConfigError(ProviderError):
    """Configuration error: decryption failure, invalid config, missing credentials."""


class ProviderConnectionError(ProviderError):
    """Connection error: timeout, network unreachable, server error."""


class NoActiveProviderError(ProviderError):
    def __init__(self) -> None:
        super().__init__(
            "No active provider selected. Please configure a provider and select a model."
        )


class ModelNotFoundError(ProviderError):
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        super().__init__(f"Model '{model_id}' not found")


class ModelNameConflictError(ProviderError):
    def __init__(self, name: str, provider_id: str) -> None:
        self.name = name
        self.provider_id = provider_id
        super().__init__(
            f"Model '{name}' already exists under provider '{provider_id}'"
        )
