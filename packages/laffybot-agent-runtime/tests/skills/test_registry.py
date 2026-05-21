"""Tests for SkillRegistry — cache, enabled/disabled, Protocol."""

from __future__ import annotations

import pytest

from laffybot_agent_runtime.skills.registry import SkillRegistry


class _MockStore:
    """Minimal SkillRegistryStore implementation."""

    def __init__(self) -> None:
        self._skills: list[str] = ["skill_a", "skill_b"]

    async def get_enabled_skills(self) -> list[str]:
        return list(self._skills)

    async def set_enabled_skills(self, skills: list[str]) -> None:
        self._skills = list(skills)


class TestSkillRegistry:
    @pytest.mark.asyncio
    async def test_get_enabled_skills_from_store(self) -> None:
        store = _MockStore()
        registry = SkillRegistry(store)
        skills = await registry.get_enabled_skills()
        assert skills == ["skill_a", "skill_b"]

    @pytest.mark.asyncio
    async def test_cache_hits_after_first_call(self) -> None:
        store = _MockStore()
        registry = SkillRegistry(store)
        await registry.get_enabled_skills()  # warms cache
        store._skills = ["only_new"]  # bypasses cache
        skills = await registry.get_enabled_skills()
        assert skills == ["skill_a", "skill_b"]  # cached value

    @pytest.mark.asyncio
    async def test_refresh_cache_clears(self) -> None:
        store = _MockStore()
        registry = SkillRegistry(store)
        await registry.get_enabled_skills()
        store._skills = ["new_skill"]
        registry.refresh_cache()
        skills = await registry.get_enabled_skills()
        assert skills == ["new_skill"]

    @pytest.mark.asyncio
    async def test_set_enabled_adds_skill(self) -> None:
        store = _MockStore()
        registry = SkillRegistry(store)
        await registry.set_enabled("skill_c", enabled=True)
        skills = await registry.get_enabled_skills()
        assert "skill_c" in skills

    @pytest.mark.asyncio
    async def test_set_disabled_removes_skill(self) -> None:
        store = _MockStore()
        registry = SkillRegistry(store)
        await registry.set_enabled("skill_a", enabled=False)
        skills = await registry.get_enabled_skills()
        assert "skill_a" not in skills

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        store = _MockStore()
        registry = SkillRegistry(store)
        assert await registry.is_enabled("skill_a") is True
        assert await registry.is_enabled("nonexistent") is False


class TestSkillRegistryStoreProtocol:
    """Any object with get_enabled_skills / set_enabled_skills satisfies the Protocol.

    Note: SkillRegistryStore is NOT @runtime_checkable, so isinstance() cannot be
    used at runtime. Static type checkers (mypy, pyright) verify conformance.
    """

    def test_protocol_methods_match(self) -> None:
        import inspect

        store = _MockStore()
        protocol_methods = {"get_enabled_skills", "set_enabled_skills"}
        for name in protocol_methods:
            assert hasattr(store, name), f"Missing method: {name}"
            assert inspect.iscoroutinefunction(getattr(store, name)), (
                f"Not async: {name}"
            )
