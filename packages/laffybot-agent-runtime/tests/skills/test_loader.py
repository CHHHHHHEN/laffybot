"""Tests for SkillsLoader — discovery, parsing, caching."""

from __future__ import annotations

from pathlib import Path

from laffybot_agent_runtime.skills.loader import SkillsLoader


def _create_skill(
    dir: Path, name: str, description: str, content: str = "body"
) -> Path:
    skill_dir = dir / name
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{content}"
    )
    return skill_file


class TestDiscoverSkills:
    def test_discovers_skills(self, tmp_path: Path) -> None:
        _create_skill(tmp_path, "test-skill", "A test skill")
        loader = SkillsLoader()
        skills = loader.discover_skills(str(tmp_path))
        assert len(skills) == 1
        assert skills[0].name == "test-skill"
        assert skills[0].description == "A test skill"

    def test_empty_directory(self, tmp_path: Path) -> None:
        loader = SkillsLoader()
        skills = loader.discover_skills(str(tmp_path))
        assert skills == []

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        loader = SkillsLoader()
        skills = loader.discover_skills(str(tmp_path / "nonexistent"))
        assert skills == []

    def test_caches_results(self, tmp_path: Path) -> None:
        _create_skill(tmp_path, "skill1", "desc")
        loader = SkillsLoader()
        loader.discover_skills(str(tmp_path))
        # Add another skill after first discovery
        _create_skill(tmp_path, "skill2", "desc")
        # Without refresh, cache should still return only skill1
        skills = loader.discover_skills(str(tmp_path))
        assert len(skills) == 1

    def test_refresh_clears_cache(self, tmp_path: Path) -> None:
        _create_skill(tmp_path, "skill1", "desc")
        loader = SkillsLoader()
        loader.discover_skills(str(tmp_path))
        _create_skill(tmp_path, "skill2", "desc")
        loader.refresh()
        skills = loader.discover_skills(str(tmp_path))
        assert len(skills) == 2

    def test_duplicate_name_warning(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "SKILL.md").write_text(
            "---\nname: same\ndescription: first\n---\n"
        )
        (tmp_path / "b").mkdir()
        (tmp_path / "b" / "SKILL.md").write_text(
            "---\nname: same\ndescription: second\n---\n"
        )
        loader = SkillsLoader()
        skills = loader.discover_skills(str(tmp_path))
        # Last one wins
        assert len(skills) == 1
        assert skills[0].description == "second"


class TestGetSkill:
    def test_get_skill_returns_skill(self, tmp_path: Path) -> None:
        _create_skill(tmp_path, "my-skill", "desc", "content body")
        loader = SkillsLoader()
        loader.discover_skills(str(tmp_path))
        skill = loader.get_skill("my-skill")
        assert skill is not None
        assert skill.metadata.name == "my-skill"
        assert skill.content == "content body"

    def test_get_skill_nonexistent(self, tmp_path: Path) -> None:
        loader = SkillsLoader()
        loader.discover_skills(str(tmp_path))
        assert loader.get_skill("nonexistent") is None

    def test_get_skill_before_discover(self) -> None:
        loader = SkillsLoader()
        assert loader.get_skill("anything") is None


class TestLoadContent:
    def test_load_content_returns_formatted(self, tmp_path: Path) -> None:
        _create_skill(tmp_path, "sk", "desc", "body content")
        loader = SkillsLoader()
        loader.discover_skills(str(tmp_path))
        result = loader.load_content("sk")
        assert "<skill_content" in result
        assert "body content" in result

    def test_load_content_nonexistent(self, tmp_path: Path) -> None:
        loader = SkillsLoader()
        loader.discover_skills(str(tmp_path))
        result = loader.load_content("nonexistent")
        assert "Error" in result


class TestLoadResource:
    def test_load_resource(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "sk"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: sk\ndescription: d\n---\nbody")
        ref_dir = skill_dir / "references"
        ref_dir.mkdir()
        (ref_dir / "ref.txt").write_text("reference content")
        loader = SkillsLoader()
        loader.discover_skills(str(tmp_path))
        result = loader.load_resource("sk", "references/ref.txt")
        assert "reference content" in result

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        _create_skill(tmp_path, "sk", "desc")
        (tmp_path / "secret.txt").write_text("secret")
        loader = SkillsLoader()
        loader.discover_skills(str(tmp_path))
        result = loader.load_resource("sk", "../secret.txt")
        assert "Error" in result or "denied" in result.lower()
