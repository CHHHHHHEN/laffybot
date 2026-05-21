"""Skill enabled-state management backed by a persistence protocol."""

from __future__ import annotations

from typing import Protocol


class SkillRegistryStore(Protocol):
    """Persistence abstraction for skill enabled-state."""

    async def get_enabled_skills(self) -> list[str]: ...
    async def set_enabled_skills(self, skills: list[str]) -> None: ...


class SkillRegistry:
    """Manage per-skill enabled/disabled state.

    The enabled-skills list is persisted via a ``SkillRegistryStore`` and
    cached in-memory for the lifetime of the registry.
    """

    def __init__(self, store: SkillRegistryStore) -> None:
        self._store = store
        self._enabled_cache: list[str] | None = None

    async def get_enabled_skills(self) -> list[str]:
        """Return the list of enabled skill names."""
        if self._enabled_cache is not None:
            return self._enabled_cache
        self._enabled_cache = await self._store.get_enabled_skills()
        return self._enabled_cache

    async def set_enabled(self, name: str, enabled: bool) -> None:
        """Enable or disable a single skill."""
        skills = await self.get_enabled_skills()
        if enabled:
            if name not in skills:
                skills.append(name)
        else:
            skills = [s for s in skills if s != name]
        self._enabled_cache = skills
        await self._store.set_enabled_skills(skills)

    async def is_enabled(self, name: str) -> bool:
        """Check whether a skill is currently enabled."""
        skills = await self.get_enabled_skills()
        return name in skills

    def refresh_cache(self) -> None:
        """Drop the in-memory cache so the next call re-reads from storage."""
        self._enabled_cache = None
