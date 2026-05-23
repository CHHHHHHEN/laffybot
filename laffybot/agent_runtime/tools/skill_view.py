"""Skill-view tool: allows the LLM to load skill content on demand."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from laffybot.agent_runtime.skills.loader import SkillsLoader
from laffybot.agent_runtime.skills.registry import SkillRegistry
from laffybot.agent_runtime.tools.base import Tool, tool_parameters


class SkillViewParams(BaseModel):
    name: str = Field(description="Skill name to load")
    file_path: str | None = Field(
        default=None,
        description="Optional resource file path relative to the skill directory",
    )


@tool_parameters(SkillViewParams)
class SkillViewTool(Tool):
    """Tool that loads skill content or resource files.

    Registered with ``kind = "skill"`` so its output is protected from
    context pruning via ``compress_protected_tools``.
    """

    kind: Literal["builtin", "mcp", "skill"] = "skill"

    def __init__(
        self,
        loader: SkillsLoader,
        registry: SkillRegistry,
    ) -> None:
        self._loader = loader
        self._registry = registry

    @property
    def name(self) -> str:
        return "skill_view"

    @property
    def description(self) -> str:
        return (
            "Load the full content of a skill or a resource file within a skill. "
            "Use this when you need the complete instructions for a skill whose "
            "metadata has been provided in the system prompt."
        )

    async def execute(self, **kwargs: str | None) -> str:
        name = kwargs.get("name", "")
        file_path = kwargs.get("file_path")

        if not name:
            return "Error: Skill name is required"

        if not await self._registry.is_enabled(name):
            return f"Error: Skill '{name}' is not enabled or not found"

        if file_path:
            return self._loader.load_resource(name, file_path)
        return self._loader.load_content(name)
