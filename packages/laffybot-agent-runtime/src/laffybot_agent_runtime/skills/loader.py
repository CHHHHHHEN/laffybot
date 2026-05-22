"""Skills directory scanning, metadata parsing, and content loading."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger

from laffybot_agent_runtime.skills.models import Skill, SkillMetadata

_YAML_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


class SkillsLoader:
    """Discover, cache, and load skills from a directory on disk.

    Responsibilities:
    - Scan a directory for ``SKILL.md`` files
    - Parse YAML frontmatter (name, description)
    - Cache discovered metadata
    - Load full content or resource files on demand
    """

    def __init__(self) -> None:
        self._cache: dict[str, SkillMetadata] | None = None
        self._cache_path: str | None = None

    def discover_skills(self, path: str) -> list[SkillMetadata]:
        """Scan *path* for skills and return their metadata.

        Results are cached.  Call ``refresh()`` to force a re-scan.
        """
        if self._cache is not None and self._cache_path == path:
            return list(self._cache.values())

        skills_dir = Path(path).expanduser().resolve()

        if not skills_dir.is_dir():
            self._cache = {}
            self._cache_path = path
            return []

        result: dict[str, SkillMetadata] = {}
        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_file = entry / "SKILL.md"
            if not skill_file.is_file():
                continue
            try:
                metadata = self._parse_skill_file(skill_file)
                if metadata is not None:
                    if metadata.name in result:
                        logger.warning(
                            "Duplicate skill name '{}' found in '{}', overwriting previous",
                            metadata.name,
                            str(entry),
                        )
                    result[metadata.name] = metadata
            except Exception:
                logger.warning(
                    "Failed to parse skill: path={}", str(skill_file), exc_info=True
                )

        self._cache = result
        self._cache_path = path
        return list(result.values())

    def get_skill(self, name: str) -> Skill | None:
        """Return full ``Skill`` (metadata + content) by name, or ``None``."""
        if self._cache is None:
            return None
        metadata = self._cache.get(name)
        if metadata is None:
            return None
        content = self._load_content_from_path(metadata.path)
        if content is None:
            return None
        return Skill(metadata=metadata, content=content)

    def load_content(self, name: str) -> str:
        """Load SKILL.md body for *name*.

        Returns the content wrapped in ``<skill_content>`` or an ``"Error:"``
        string on failure.
        """
        if self._cache is None:
            return "Error: No skills discovered. Call discover_skills() first."
        metadata = self._cache.get(name)
        if metadata is None:
            return f"Error: Skill '{name}' not found"
        content = self._load_content_from_path(metadata.path)
        if content is None:
            return f"Error: Failed to load content for skill '{name}'"
        return self._format_content(name, content)

    def load_resource(self, name: str, file_path: str) -> str:
        """Load a resource file from skill *name*'s directory.

        *file_path* is relative to the skill's root directory.
        Returns the content wrapped in ``<skill_resource>`` or an ``"Error:"``
        string on failure.
        """
        if self._cache is None:
            return "Error: No skills discovered. Call discover_skills() first."
        metadata = self._cache.get(name)
        if metadata is None:
            return f"Error: Skill '{name}' not found"

        skill_dir = Path(metadata.path).parent.resolve()

        # Path traversal protection
        requested = (skill_dir / file_path).resolve()
        if not str(requested).startswith(str(skill_dir)):
            return "Error: Permission denied: file path is outside skill directory"

        if not requested.is_file():
            return f"Error: Resource file not found: {file_path}"

        try:
            content = requested.read_text(encoding="utf-8")
            return self._format_resource(name, file_path, content)
        except Exception as e:
            return f"Error: Failed to read resource file: {e}"

    def refresh(self) -> None:
        """Clear cached metadata.  Next ``discover_skills()`` re-scans."""
        self._cache = None
        self._cache_path = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_skill_file(self, path: Path) -> SkillMetadata | None:
        """Parse a single SKILL.md and return its metadata, or ``None``."""
        content = path.read_text(encoding="utf-8")
        match = _YAML_FRONTMATTER_RE.match(content)
        if not match:
            logger.warning("SKILL.md missing YAML frontmatter: path={}", str(path))
            return None

        yaml_text = match.group(1)

        fields = self._parse_simple_yaml(yaml_text)

        name = fields.get("name")
        description = fields.get("description")

        if not name or not description:
            logger.warning(
                "SKILL.md missing required fields (name, description): path={}",
                str(path),
            )
            return None

        ref_dir = path.parent / "references"
        has_resources = ref_dir.is_dir() and any(ref_dir.iterdir())

        return SkillMetadata(
            name=str(name).strip(),
            description=str(description).strip(),
            path=str(path),
            has_resources=has_resources,
        )

    def _load_content_from_path(self, path: str) -> str | None:
        """Read a SKILL.md file and return its body (without frontmatter)."""
        try:
            p = Path(path)
            if not p.is_file():
                return None
            content = p.read_text(encoding="utf-8")
            match = _YAML_FRONTMATTER_RE.match(content)
            if match:
                return match.group(2).strip()
            return content.strip()
        except Exception:
            logger.warning(
                "Failed to read skill content from path={}", path, exc_info=True
            )
            return None

    @staticmethod
    def _parse_simple_yaml(text: str) -> dict[str, Any]:
        """Minimal YAML key-value parser for frontmatter.

        Handles the subset needed for SKILL.md frontmatter (name, description).
        """
        result: dict[str, Any] = {}
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    result[key] = value
        return result

    @staticmethod
    def _format_content(name: str, content: str) -> str:
        return f'<skill_content name="{name}">\n{content}\n</skill_content>'

    @staticmethod
    def _format_resource(name: str, file_path: str, content: str) -> str:
        return (
            f'<skill_resource name="{name}" path="{file_path}">\n'
            f"{content}\n"
            f"</skill_resource>"
        )
