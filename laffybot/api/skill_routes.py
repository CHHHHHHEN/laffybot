"""Skill management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from laffybot_agent_runtime.skills import SkillRegistry, SkillsLoader

from laffybot.api.dependencies import (
    get_app_setting_store,
    get_skill_registry,
    get_skills_loader,
)
from laffybot.api.schemas import (
    SkillEnabledUpdateRequest,
    SkillItem,
    SkillsListResponse,
    SkillsPathResponse,
    SkillsPathUpdateRequest,
)
from laffybot.session.app_setting_store import AppSettingStore

router = APIRouter()


@router.get("/settings/skills-path")
async def get_skills_path(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
) -> SkillsPathResponse:
    path = await app_setting_store.get_skills_path()
    return SkillsPathResponse(path=path)


@router.put("/settings/skills-path", response_model=SkillsListResponse)
async def set_skills_path(
    body: SkillsPathUpdateRequest,
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
    skills_loader: SkillsLoader = Depends(get_skills_loader),
    skill_registry: SkillRegistry = Depends(get_skill_registry),
) -> SkillsListResponse:
    await app_setting_store.set_skills_path(body.path)
    skills_loader.refresh()
    all_skills = skills_loader.discover_skills(body.path)
    enabled = await skill_registry.get_enabled_skills()
    items = [
        SkillItem(
            name=s.name,
            description=s.description,
            enabled=s.name in enabled,
            has_resources=s.has_resources,
        )
        for s in all_skills
    ]
    return SkillsListResponse(skills=items, skills_path=body.path)


@router.get("/skills")
async def list_skills(
    app_setting_store: AppSettingStore = Depends(get_app_setting_store),
    skills_loader: SkillsLoader = Depends(get_skills_loader),
    skill_registry: SkillRegistry = Depends(get_skill_registry),
) -> SkillsListResponse:
    skills_path = await app_setting_store.get_skills_path()
    if not skills_path:
        return SkillsListResponse(skills=[], skills_path=None)

    all_skills = skills_loader.discover_skills(skills_path)
    enabled = await skill_registry.get_enabled_skills()

    items = [
        SkillItem(
            name=s.name,
            description=s.description,
            enabled=s.name in enabled,
            has_resources=s.has_resources,
        )
        for s in all_skills
    ]
    return SkillsListResponse(skills=items, skills_path=skills_path)


@router.put("/skills/{name}/enabled")
async def set_skill_enabled(
    name: str,
    body: SkillEnabledUpdateRequest,
    skill_registry: SkillRegistry = Depends(get_skill_registry),
) -> SkillEnabledUpdateRequest:
    await skill_registry.set_enabled(name, body.enabled)
    return SkillEnabledUpdateRequest(enabled=body.enabled)
