from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


class ProviderConfig(BaseSettings):
    api_key: str
    base_url: str
    extra_headers: dict[str, str] = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)
