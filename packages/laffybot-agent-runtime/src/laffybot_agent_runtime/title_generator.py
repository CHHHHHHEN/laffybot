"""Title generation service for sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from laffybot_agent_runtime.providers.types import ErrorLLMResponse

if TYPE_CHECKING:
    from laffybot_agent_runtime.providers.base import BaseProvider

TITLE_PROMPT = """Generate a concise, descriptive title (max 50 characters) for this conversation. Respond with ONLY the title, no quotes or punctuation.

Conversation:
{conversation}

Title:"""


class TitleGenerator:
    """Generates session titles using LLM."""

    def __init__(self, provider: BaseProvider, model: str):
        self.provider = provider
        self.model = model

    async def generate_title(
        self,
        messages: list[dict[str, str]],
    ) -> str | None:
        """Generate a title from conversation messages.

        Args:
            messages: List of messages with 'role' and 'content' keys.

        Returns:
            Generated title string, or None if generation failed.
        """
        # Build conversation text
        conversation_parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                conversation_parts.append(f"{role}: {content}")

        if not conversation_parts:
            return None

        conversation_text = "\n".join(conversation_parts)
        prompt = TITLE_PROMPT.format(conversation=conversation_text)

        try:
            response = await self.provider.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.7,
                max_tokens=50,
            )

            if isinstance(response, ErrorLLMResponse):
                logger.warning(
                    "Title generation failed: error_kind={}",
                    response.error_kind,
                )
                return None

            if response.content:
                title = response.content.strip()
                # Remove quotes if present
                if title.startswith('"') and title.endswith('"'):
                    title = title[1:-1]
                if title.startswith("'") and title.endswith("'"):
                    title = title[1:-1]
                # Truncate to 100 chars max
                return title[:100]

            return None

        except Exception as e:
            logger.warning("Title generation failed: {}", str(e))
            return None

    @staticmethod
    def truncate_title_from_message(content: str, max_length: int = 50) -> str:
        """Generate a fallback title by truncating user message.

        Args:
            content: User message content.
            max_length: Maximum title length.

        Returns:
            Truncated title string.
        """
        # Remove newlines and extra spaces
        title = " ".join(content.split())
        # Truncate
        if len(title) > max_length:
            title = title[:max_length].rstrip() + "..."
        return title
