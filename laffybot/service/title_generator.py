"""Title generation service (service layer)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from laffybot_agent_runtime.providers.base import BaseProvider

TITLE_PROMPT = """Generate a concise, descriptive title (max 50 characters) for this conversation. Respond with ONLY the title, no quotes or punctuation.

Conversation:
{conversation}

Title:"""


class TitleGenerator:
    def __init__(self, provider: BaseProvider, model: str):
        self.provider = provider
        self.model = model

    async def generate_title(
        self,
        messages: list[dict[str, str]],
    ) -> str | None:
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
            from laffybot_agent_runtime.providers.types import ErrorLLMResponse

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
                if title.startswith('"') and title.endswith('"'):
                    title = title[1:-1]
                if title.startswith("'") and title.endswith("'"):
                    title = title[1:-1]
                return title[:100]

            return None

        except Exception as e:
            logger.warning("Title generation failed: {}", str(e))
            return None

    @staticmethod
    def truncate_title_from_message(content: str, max_length: int = 50) -> str:
        title = " ".join(content.split())
        if len(title) > max_length:
            title = title[:max_length].rstrip() + "..."
        return title
