"""Types for context building."""

from dataclasses import dataclass, field

from laffybot_agent_runtime.config import ContextConfig


@dataclass
class RegionInfo:
    message_ids: list[int] = field(default_factory=list)
    token_ratio: float = 0.0


__all__ = ["ContextConfig", "RegionInfo"]
