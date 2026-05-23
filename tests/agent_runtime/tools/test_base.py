"""Tests for Tool ABC and tool_parameters decorator."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field, ValidationError

from laffybot.agent_runtime.tools.base import (
    Tool,
    _format_pydantic_errors,
    tool_parameters,
)


class TestAbstractBase:
    """Tool ABC cannot be instantiated without abstract methods."""

    def test_cannot_instantiate_without_name(self) -> None:
        with pytest.raises(TypeError, match="abstract.*name"):
            Tool()  # type: ignore[abstract]

    def test_cannot_instantiate_without_execute(self) -> None:
        class _NoExecute(Tool):
            @property
            def name(self) -> str:
                return "no_exec"

            @property
            def description(self) -> str:
                return "No execute"

        with pytest.raises(TypeError, match="abstract.*execute"):
            _NoExecute()  # type: ignore[abstract]

    def test_can_instantiate_with_all_abstract(self) -> None:
        class _FullTool(Tool):
            @property
            def name(self) -> str:
                return "full"

            @property
            def description(self) -> str:
                return "Full tool"

            async def execute(self, **kwargs: Any) -> str:
                return "ok"

        t = _FullTool()
        assert t.name == "full"
        assert t.description == "Full tool"


class TestDefaults:
    """Default property values for read_only, concurrency_safe, exclusive."""

    def _make_tool(self) -> Tool:
        class _T(Tool):
            @property
            def name(self) -> str:
                return "t"

            @property
            def description(self) -> str:
                return "t"

            async def execute(self, **kwargs: Any) -> str:
                return "ok"

        return _T()

    def test_default_read_only(self) -> None:
        assert self._make_tool().read_only is False

    def test_default_exclusive(self) -> None:
        assert self._make_tool().exclusive is False

    def test_concurrency_safe_default(self) -> None:
        assert self._make_tool().concurrency_safe is False

    def test_concurrency_safe_requires_read_only_and_not_exclusive(self) -> None:
        class _ReadOnlyTool(Tool):
            @property
            def name(self) -> str:
                return "ro"

            @property
            def description(self) -> str:
                return "ro"

            @property
            def read_only(self) -> bool:
                return True

            async def execute(self, **kwargs: Any) -> str:
                return "ok"

        t = _ReadOnlyTool()
        assert t.read_only is True
        assert t.exclusive is False
        assert t.concurrency_safe is True

    def test_exclusive_disables_concurrency_safe(self) -> None:
        class _ExclusiveReadOnly(Tool):
            @property
            def name(self) -> str:
                return "er"

            @property
            def description(self) -> str:
                return "er"

            @property
            def read_only(self) -> bool:
                return True

            @property
            def exclusive(self) -> bool:
                return True

            async def execute(self, **kwargs: Any) -> str:
                return "ok"

        t = _ExclusiveReadOnly()
        assert t.concurrency_safe is False


class TestParameters:
    """parameters property and to_schema."""

    def test_no_param_model_returns_empty_schema(self) -> None:
        class _NoParams(Tool):
            @property
            def name(self) -> str:
                return "np"

            @property
            def description(self) -> str:
                return "np"

            async def execute(self, **kwargs: Any) -> str:
                return "ok"

        t = _NoParams()
        assert t.parameters == {"type": "object", "properties": {}}

    def test_to_schema_format(self) -> None:
        class _Simple(Tool):
            @property
            def name(self) -> str:
                return "simple"

            @property
            def description(self) -> str:
                return "A simple tool"

            async def execute(self, **kwargs: Any) -> str:
                return "ok"

        t = _Simple()
        schema = t.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "simple"
        assert schema["function"]["description"] == "A simple tool"
        assert "parameters" in schema["function"]


class _TestParams(BaseModel):
    path: str = Field(description="The path")
    count: int = Field(default=1, ge=1, description="Count")


@tool_parameters(_TestParams)
class _ParametrizedTool(Tool):
    @property
    def name(self) -> str:
        return "param"

    @property
    def description(self) -> str:
        return "Has params"

    async def execute(self, **kwargs: Any) -> str:
        return f"executed with {kwargs}"


class TestToolParametersDecorator:
    """@tool_parameters sets _param_model and generates schema."""

    def test_sets_param_model(self) -> None:
        assert _ParametrizedTool._param_model is _TestParams

    def test_parameters_has_schema(self) -> None:
        t = _ParametrizedTool()
        schema = t.parameters
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "count" in schema["properties"]
        assert schema["properties"]["path"].get("description") == "The path"

    def test_parameters_no_longer_abstract(self) -> None:
        t = _ParametrizedTool()
        assert t.parameters is not None  # would raise if still abstract

    def test_cast_params_success(self) -> None:
        t = _ParametrizedTool()
        result = t.cast_params({"path": "/tmp", "count": "3"})
        assert result["path"] == "/tmp"
        assert result["count"] == 3  # coerced from str to int

    def test_cast_params_failure(self) -> None:
        t = _ParametrizedTool()
        with pytest.raises(Exception):
            t.cast_params({"path": "/tmp", "count": 0})  # ge=1 violation

    def test_validate_params_success(self) -> None:
        t = _ParametrizedTool()
        errors = t.validate_params({"path": "/tmp", "count": 2})
        assert errors == []

    def test_validate_params_failure(self) -> None:
        t = _ParametrizedTool()
        errors = t.validate_params({"path": "/tmp", "count": 0})
        assert len(errors) >= 1
        assert "count" in errors[0]

    def test_validate_params_missing_required(self) -> None:
        t = _ParametrizedTool()
        errors = t.validate_params({})
        assert len(errors) >= 1
        assert "path" in errors[0]


class TestNoParamModelBehavior:
    """Tools without _param_model handle params directly."""

    def _make_no_param_tool(self) -> Tool:
        class _T(Tool):
            @property
            def name(self) -> str:
                return "raw"

            @property
            def description(self) -> str:
                return "raw"

            async def execute(self, **kwargs: Any) -> str:
                return "ok"

        return _T()

    def test_cast_params_passthrough(self) -> None:
        t = self._make_no_param_tool()
        result = t.cast_params({"a": 1})
        assert result == {"a": 1}

    def test_validate_params_empty_for_dict(self) -> None:
        t = self._make_no_param_tool()
        assert t.validate_params({"a": 1}) == []

    def test_validate_params_rejects_non_dict(self) -> None:
        t = self._make_no_param_tool()
        errors = t.validate_params("not a dict")  # type: ignore[arg-type]
        assert errors == ["parameters must be an object"]

    def test_parameters_empty_schema(self) -> None:
        t = self._make_no_param_tool()
        assert t.parameters == {"type": "object", "properties": {}}


class TestFormatPydanticErrors:
    """_format_pydantic_errors helper."""

    def test_single_error(self) -> None:
        try:
            _TestParams(path="ok", count=0)
        except ValidationError as e:
            errors = _format_pydantic_errors(e)
            assert len(errors) >= 1
            assert any("count" in err for err in errors)

    def test_multiple_errors(self) -> None:
        try:
            _TestParams(path=123, count=-1)  # type: ignore[arg-type]
        except ValidationError as e:
            errors = _format_pydantic_errors(e)
            assert len(errors) >= 2

    def test_error_format(self) -> None:
        try:
            _TestParams(path="ok", count=0)
        except ValidationError as e:
            errors = _format_pydantic_errors(e)
            for err in errors:
                assert isinstance(err, str)
                assert len(err) > 0
