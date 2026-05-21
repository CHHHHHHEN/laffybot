"""Provider configuration domain model for constructing provider instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderConfig:
    """Resolved provider configuration with decrypted API key.

    This is the domain model used to instantiate BaseProvider implementations,
    distinct from the pydantic-settings based ProviderConfig used for env loading.
    """

    provider_id: str
    name: str
    api_key: str
    base_url: str
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
