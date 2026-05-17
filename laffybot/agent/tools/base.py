"""Base class for agent tools with Pydantic parameter models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError
from pydantic.type_adapter import TypeAdapter

_ToolT = TypeVar("_ToolT", bound="Tool")


class Tool(ABC):
    """Agent capability: read files, run commands, etc.

    Subclasses set ``_param_model`` (a Pydantic ``BaseModel`` subclass) either
    directly or via the ``@tool_parameters`` decorator.  The ``parameters``
    property generates a JSON Schema from the model, and ``cast_params`` /
    ``validate_params`` delegate to Pydantic.
    """

    _param_model: type[BaseModel] | None = None

    kind: Literal["builtin", "mcp"] = "builtin"

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does."""
        ...

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters, derived from ``_param_model``."""
        if self._param_model is None:
            return {"type": "object", "properties": {}}
        schema = TypeAdapter(self._param_model).json_schema()
        return schema

    @property
    def read_only(self) -> bool:
        """Whether this tool is side-effect free and safe to parallelize."""
        return False

    @property
    def concurrency_safe(self) -> bool:
        """Whether this tool can run alongside other concurrency-safe tools."""
        return self.read_only and not self.exclusive

    @property
    def exclusive(self) -> bool:
        """Whether this tool should run alone even if concurrency is enabled."""
        return False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Run the tool; returns a string or list of content blocks."""
        ...

    def cast_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate and coerce params via the Pydantic model."""
        if self._param_model is None:
            return params
        validated = self._param_model.model_validate(params)
        return validated.model_dump()

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate against the Pydantic model; empty list means valid."""
        if self._param_model is None:
            if not isinstance(params, dict):
                return ["parameters must be an object"]
            return []
        try:
            self._param_model.model_validate(params)
            return []
        except ValidationError as e:
            fmt = _format_pydantic_errors(e)
            return fmt

    def to_schema(self) -> dict[str, Any]:
        """OpenAI function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _format_pydantic_errors(exc: ValidationError) -> list[str]:
    """Format Pydantic validation errors into human-readable strings."""
    result: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"])
        result.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return result


def tool_parameters(
    model_class: type[BaseModel],
) -> Callable[[type[_ToolT]], type[_ToolT]]:
    """Class decorator: attach a Pydantic model for parameter schema/validation.

    Use on ``Tool`` subclasses::

        class ReadFileParams(BaseModel):
            path: str = Field(description="The file path")
            ...

        @tool_parameters(ReadFileParams)
        class ReadFileTool(Tool):
            ...

    The ``parameters`` property is automatically provided from the model's
    JSON Schema, and ``cast_params`` / ``validate_params`` use Pydantic.
    """

    def decorator(cls: type[_ToolT]) -> type[_ToolT]:
        cls._param_model = model_class

        abstract = getattr(cls, "__abstractmethods__", None)
        if abstract is not None and "parameters" in abstract:
            cls.__abstractmethods__ = frozenset(abstract - {"parameters"})

        return cls

    return decorator
