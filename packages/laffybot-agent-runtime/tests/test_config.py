"""Tests for ContextConfig Pydantic model."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from laffybot_agent_runtime.config import ContextConfig


class TestDefaults:
    """Default construction — all fields match declared defaults."""

    def test_default_values(self) -> None:
        config = ContextConfig()
        assert config.max_tokens is None
        assert config.max_messages is None
        assert config.system_prompt == "You are a helpful assistant."
        assert config.system_prompt_template is not None
        assert config.template_variables == {}
        assert config.use_exact_token_count is True
        assert config.enable_compression is True
        assert config.compress_threshold_ratio == 0.8
        assert config.compress_preserve_pairs == 3
        assert config.compress_preserve_recent_tokens is None
        assert config.compress_reserved_tokens == 20000
        assert config.compress_max_summary_tokens == 512
        assert config.compress_model is None
        assert config.compress_tool_output_max_chars == 2000
        assert config.compress_protected_tools == ["skill"]
        assert config.request_timeout_seconds == 600.0


class TestCustomAssignment:
    """Each field can be set to a non-default value."""

    def test_all_fields_custom(self) -> None:
        config = ContextConfig(
            max_tokens=10000,
            max_messages=50,
            system_prompt="Custom prompt",
            system_prompt_template=None,
            template_variables={"key": "value"},
            use_exact_token_count=False,
            enable_compression=False,
            compress_threshold_ratio=0.5,
            compress_preserve_pairs=5,
            compress_preserve_recent_tokens=2000,
            compress_reserved_tokens=10000,
            compress_max_summary_tokens=256,
            compress_model="gpt-4o-mini",
            compress_tool_output_max_chars=500,
            compress_protected_tools=["skill", "mcp"],
            request_timeout_seconds=120.0,
        )
        assert config.max_tokens == 10000
        assert config.max_messages == 50
        assert config.system_prompt == "Custom prompt"
        assert config.system_prompt_template is None
        assert config.template_variables == {"key": "value"}
        assert config.use_exact_token_count is False
        assert config.enable_compression is False
        assert config.compress_threshold_ratio == 0.5
        assert config.compress_preserve_pairs == 5
        assert config.compress_preserve_recent_tokens == 2000
        assert config.compress_reserved_tokens == 10000
        assert config.compress_max_summary_tokens == 256
        assert config.compress_model == "gpt-4o-mini"
        assert config.compress_tool_output_max_chars == 500
        assert config.compress_protected_tools == ["skill", "mcp"]
        assert config.request_timeout_seconds == 120.0


class TestFieldConstraints:
    """Pydantic ge/le constraints reject invalid values."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("compress_threshold_ratio", -0.1),
            ("compress_threshold_ratio", 1.1),
            ("compress_preserve_pairs", 0),
            ("compress_reserved_tokens", -1),
            ("compress_max_summary_tokens", 0),
            ("compress_tool_output_max_chars", -1),
            ("request_timeout_seconds", 0.5),
        ],
    )
    def test_below_minimum_rejected(self, field: str, value: Any) -> None:
        with pytest.raises(ValidationError):
            ContextConfig(**{field: value})

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("compress_threshold_ratio", 0.0),
            ("compress_threshold_ratio", 1.0),
            ("compress_preserve_pairs", 1),
            ("compress_reserved_tokens", 0),
            ("compress_max_summary_tokens", 1),
            ("compress_tool_output_max_chars", 0),
            ("request_timeout_seconds", 1.0),
        ],
    )
    def test_boundary_values_accepted(self, field: str, value: Any) -> None:
        config = ContextConfig(**{field: value})
        assert getattr(config, field) == value


class TestTypeCoercion:
    """Pydantic v2 coerces compatible types — verify result."""

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [
            ("use_exact_token_count", "true", True),
            ("enable_compression", 1, True),
            ("compress_threshold_ratio", "0.5", 0.5),
            ("request_timeout_seconds", "600", 600.0),
        ],
    )
    def test_type_coercion(self, field: str, value: Any, expected: Any) -> None:
        config = ContextConfig(**{field: value})
        assert getattr(config, field) == expected


class TestTypeRejection:
    """Incompatible types still raise ValidationError."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("max_tokens", "not_a_number"),
            ("system_prompt", 42),
            ("compress_preserve_pairs", 3.5),
            ("compress_protected_tools", "not_a_list"),
        ],
    )
    def test_wrong_type_rejected(self, field: str, value: Any) -> None:
        with pytest.raises(ValidationError):
            ContextConfig(**{field: value})


class TestPartialConstruction:
    """Partial construction fills remaining fields with defaults."""

    def test_partial_sets_defaults(self) -> None:
        config = ContextConfig(max_tokens=5000)
        assert config.max_tokens == 5000
        assert config.max_messages is None
        assert config.system_prompt == "You are a helpful assistant."

    def test_empty_is_valid(self) -> None:
        config = ContextConfig()
        assert isinstance(config, ContextConfig)
