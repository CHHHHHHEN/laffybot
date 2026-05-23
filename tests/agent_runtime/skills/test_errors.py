"""Tests for SkillError."""

from laffybot.agent_runtime.skills.errors import SkillError


def test_skill_error_is_exception() -> None:
    assert issubclass(SkillError, Exception)


def test_skill_error_message() -> None:
    err = SkillError("something went wrong")
    assert str(err) == "something went wrong"
