from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SkillMetadata:
    name: str
    description: str
    path: str
    has_resources: bool = False


@dataclass(slots=True)
class Skill:
    metadata: SkillMetadata
    content: str
