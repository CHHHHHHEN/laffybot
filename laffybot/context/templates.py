"""System prompt template support with Jinja2."""

import ast
from datetime import datetime
from typing import Any

from jinja2 import Environment, StrictUndefined

from laffybot.config import ContextConfig


class SystemPromptTemplate:
    """Render system prompts from Jinja2 templates.

    Supports dynamic variable injection for session context.
    """

    def __init__(self, config: ContextConfig):
        """Initialize template renderer.

        Args:
            config: Context configuration with template settings.
        """
        self._config = config
        self._env = Environment(
            undefined=StrictUndefined,
            autoescape=False,  # System prompts are not HTML
        )

    def render(
        self,
        session_id: str | None = None,
        model: str | None = None,
        created_at: datetime | None = None,
        **extra_vars: Any,
    ) -> str | None:
        """Render system prompt from template or return static prompt.

        Args:
            session_id: Session identifier.
            model: Model name.
            created_at: Session creation timestamp.
            **extra_vars: Additional template variables.

        Returns:
            Rendered system prompt or None if not configured.
        """
        # Priority: template > static prompt
        if self._config.system_prompt_template:
            return self._render_template(
                session_id=session_id,
                model=model,
                created_at=created_at,
                **extra_vars,
            )

        return self._config.system_prompt

    def _render_template(
        self,
        session_id: str | None,
        model: str | None,
        created_at: datetime | None,
        **extra_vars: Any,
    ) -> str:
        """Render Jinja2 template with context variables."""
        # Build variable context
        context: dict[str, Any] = {
            "session_id": session_id,
            "model": model,
            "created_at": created_at.isoformat() if created_at else None,
            "current_time": datetime.now().isoformat(),
        }

        # Add custom variables from config
        context.update(self._config.template_variables)

        # Add extra variables (highest priority)
        context.update(extra_vars)

        # Render template
        template_str = self._config.system_prompt_template
        if template_str is None:
            return ""
        template = self._env.from_string(template_str)
        return template.render(**context)

    @staticmethod
    def validate_template(template_str: str) -> list[str]:
        """Validate a Jinja2 template string.

        Args:
            template_str: Template string to validate.

        Returns:
            List of variable names used in the template.

        Raises:
            TemplateSyntaxError: If template has syntax errors.
        """
        env = Environment(undefined=StrictUndefined)
        template = env.from_string(template_str)

        # Parse the template source to extract variable names
        ast_node = env.parse(template_str)
        variables: set[str] = set()

        # Walk the AST to find Name nodes
        for node in ast.walk(ast_node):  # type: ignore
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                variables.add(node.id)

        return sorted(variables)
