"""Tests for SkillViewTool."""

from __future__ import annotations

import pytest

from laffybot_agent_runtime.skills.loader import SkillsLoader
from laffybot_agent_runtime.skills.registry import SkillRegistry
from laffybot_agent_runtime.tools.skill_view import SkillViewTool


class _Store:
    def __init__(self) -> None:
        self._skills: list[str] = ["enabled_skill"]

    async def get_enabled_skills(self) -> list[str]:
        return list(self._skills)

    async def set_enabled_skills(self, skills: list[str]) -> None:
        self._skills = list(skills)


class TestSkillViewTool:
    @pytest.mark.asyncio
    async def test_execute_empty_name_returns_error(self) -> None:
        loader = SkillsLoader()
        registry = SkillRegistry(_Store())
        tool = SkillViewTool(loader, registry)
        result = await tool.execute(name="")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_execute_disabled_skill_returns_error(self) -> None:
        loader = SkillsLoader()
        registry = SkillRegistry(_Store())
        tool = SkillViewTool(loader, registry)
        result = await tool.execute(name="disabled_skill")
        assert "Error" in result
        assert "not enabled" in result.lower()

    @pytest.mark.asyncio
    async def test_name_and_description(self) -> None:
        loader = SkillsLoader()
        registry = SkillRegistry(_Store())
        tool = SkillViewTool(loader, registry)
        assert tool.name == "skill_view"
        assert "skill" in tool.description.lower()
