"""Jinja2-based system prompt template rendering (service layer)."""

from __future__ import annotations

from typing import Any

from jinja2 import Environment as JinjaEnvironment
from jinja2 import StrictUndefined, TemplateError
from loguru import logger

from .types import ContextConfig


class SystemPromptTemplate:
    """Renders system prompt from a Jinja2 template with strict variable checking."""

    def __init__(self, config: ContextConfig):
        self._config = config
        self._env = JinjaEnvironment(undefined=StrictUndefined, autoescape=False)

    def render(self, **variables: Any) -> str:
        template_source = self._config.system_prompt_template
        if template_source is None:
            return self._config.system_prompt

        env_vars = dict(self._config.template_variables)
        env_vars.update(variables)
        try:
            template = self._env.from_string(template_source)
            return template.render(**env_vars)
        except TemplateError as exc:
            logger.warning("System prompt template rendering failed: {}", exc)
            return self._config.system_prompt
