"""Skill management API routes — delegates to SessionManager."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from laffybot.api.dependencies import get_session_manager
from laffybot.api.schemas import (
    SkillEnabledUpdateRequest,
    SkillItem,
    SkillsListResponse,
    SkillsPathResponse,
    SkillsPathUpdateRequest,
)
from laffybot.service.protocols import SessionManager

router = APIRouter()


@router.get("/settings/skills-path")
async def get_skills_path(
    manager: SessionManager = Depends(get_session_manager),
) -> SkillsPathResponse:
    path = await manager.get_skills_path()
    return SkillsPathResponse(path=path)


@router.put("/settings/skills-path", response_model=SkillsListResponse)
async def set_skills_path(
    body: SkillsPathUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> SkillsListResponse:
    skills = await manager.set_skills_path(body.path)
    return SkillsListResponse(
        skills=[SkillItem(**s) for s in skills], skills_path=body.path
    )


@router.get("/skills")
async def list_skills(
    manager: SessionManager = Depends(get_session_manager),
) -> SkillsListResponse:
    skills = await manager.list_skills()
    return SkillsListResponse(skills=[SkillItem(**s) for s in skills], skills_path=None)


@router.put("/skills/{name}/enabled")
async def set_skill_enabled(
    name: str,
    body: SkillEnabledUpdateRequest,
    manager: SessionManager = Depends(get_session_manager),
) -> SkillEnabledUpdateRequest:
    await manager.set_skill_enabled(name, body.enabled)
    return SkillEnabledUpdateRequest(enabled=body.enabled)
