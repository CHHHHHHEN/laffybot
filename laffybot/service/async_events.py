from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from loguru import logger

from laffybot.eventbus.protocol import EventPublisher
from laffybot.service.context.compressor import LLMSummarizer
from laffybot.service.context.types import RegionInfo
from laffybot.service.error_log import get_error_log
from laffybot.service.protocols import MemoryManager
from laffybot.service.provider_factory import ProviderFactory
from laffybot.service.title_generator import TitleGenerator

if TYPE_CHECKING:
    from laffybot.db.app_setting_store import AppSettingStore
    from laffybot.db.provider_store import ProviderStore
    from laffybot.db.session_store import SessionStore


class AsyncEventProcessor:
    def __init__(
        self,
        store: SessionStore,
        provider_store: ProviderStore,
        app_setting_store: AppSettingStore,
        provider_factory: ProviderFactory,
        memory_manager: MemoryManager | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._store = store
        self._provider_store = provider_store
        self._app_setting_store = app_setting_store
        self._provider_factory = provider_factory
        self._memory_manager = memory_manager
        self._event_publisher = event_publisher
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def _create_task(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)

        def _on_done(t: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(t)
            exc = t.exception()
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                logger.opt(exception=exc).error(
                    "Background task failed: {}",
                    exc,
                )
                try:
                    get_error_log().record(
                        level="ERROR",
                        source="async_events:_create_task",
                        message=f"Background task failed: {exc}",
                        error_code="BACKGROUND_TASK_FAILED",
                        exc_info=exc,
                    )
                except Exception:
                    pass  # error log should never throw

        task.add_done_callback(_on_done)
        self._background_tasks.add(task)
        return task

    async def submit_auto_title(self, session_id: str) -> asyncio.Task[Any]:
        return self._create_task(self._do_auto_title(session_id))

    async def submit_memory_extract(self, session_id: str) -> asyncio.Task[Any]:
        return self._create_task(self._do_memory_extract(session_id))

    async def submit_context_compress(
        self, session_id: str, region_info: RegionInfo, summarizer: LLMSummarizer
    ) -> asyncio.Task[Any]:
        return self._create_task(
            self._do_context_compress(session_id, region_info, summarizer)
        )

    async def submit_auto_archive(self, session_id: str) -> asyncio.Task[Any]:
        return self._create_task(self._do_auto_archive(session_id))

    async def shutdown(self) -> None:
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

    async def _do_auto_title(self, session_id: str) -> None:
        try:
            session = await self._store.get_session(session_id)

            should_generate = False
            is_first_time = session.title is None

            if is_first_time:
                messages = await self._store.get_messages(session_id)
                user_msgs = [m for m in messages if m["role"] == "user"]
                assistant_msgs = [m for m in messages if m["role"] == "assistant"]

                if not user_msgs or not assistant_msgs:
                    return

                first_assistant = assistant_msgs[0]
                if not first_assistant.get("content"):
                    return

                should_generate = True
            elif session.title_auto_generated:
                msg_increment = (
                    session.user_message_count
                    - session.title_updated_at_user_message_count
                )
                if msg_increment >= 5:
                    should_generate = True

            if not should_generate:
                return

            summary_config = await self._app_setting_store.get_summary_model()

            if summary_config is None:
                if is_first_time:
                    messages = await self._store.get_messages(session_id)
                    user_msgs = [m for m in messages if m["role"] == "user"]
                    if user_msgs and user_msgs[0].get("content"):
                        title = TitleGenerator.truncate_title_from_message(
                            user_msgs[0]["content"]
                        )
                        success = await self._store.update_session_title(
                            session_id,
                            title,
                            session.user_message_count,
                            False,
                        )
                        if success and self._event_publisher is not None:
                            await self._event_publisher.publish(
                                "title_update",
                                {"session_id": session_id, "title": title},
                            )
                return

            provider_config = await self._provider_store.get_provider_config(
                summary_config.provider_id
            )
            provider = await self._provider_factory.create_provider(provider_config)
            generator = TitleGenerator(provider, summary_config.model_name)

            messages = await self._store.get_messages(session_id, limit=1000)

            generated_title = await generator.generate_title(messages)

            if generated_title is None:
                return

            success = await self._store.update_session_title(
                session_id,
                generated_title,
                session.user_message_count,
                session.title_auto_generated,
            )

            if success:
                logger.info(
                    "Auto-title generated: session_id={}, title={}",
                    session_id,
                    generated_title,
                )
                if self._event_publisher is not None:
                    await self._event_publisher.publish(
                        "title_update",
                        {"session_id": session_id, "title": generated_title},
                    )
            else:
                logger.debug(
                    "Auto-title write skipped (optimistic lock): session_id={}",
                    session_id,
                )

        except Exception as e:
            logger.warning(
                "Auto-title generation failed: session_id={}, error={}",
                session_id,
                str(e),
            )
            get_error_log().record(
                level="WARNING",
                source="async_events:_do_auto_title",
                message=str(e),
                session_id=session_id,
                error_code="AUTO_TITLE_FAILED",
                exc_info=e,
            )

    async def _do_memory_extract(self, session_id: str) -> None:
        if self._memory_manager is None:
            return

        try:
            messages = await self._store.get_messages(session_id, limit=1000)

            extract_config = await self._app_setting_store.get_extract_model()

            if extract_config is None:
                logger.debug(
                    "Memory extraction skipped (no extract model): session_id={}",
                    session_id,
                )
                return

            provider_config = await self._provider_store.get_provider_config(
                extract_config.provider_id
            )
            provider = await self._provider_factory.create_provider(provider_config)

            await self._memory_manager.extract(
                session_id=session_id,
                messages=messages,
                provider=provider,
                model=extract_config.model_name,
            )

        except Exception as e:
            logger.warning(
                "Memory extraction failed: session_id={}, error={}",
                session_id,
                str(e),
            )
            get_error_log().record(
                level="WARNING",
                source="async_events:_do_memory_extract",
                message=str(e),
                session_id=session_id,
                error_code="MEMORY_EXTRACT_FAILED",
                exc_info=e,
            )

    async def _do_context_compress(
        self, session_id: str, region_info: RegionInfo, summarizer: LLMSummarizer
    ) -> None:
        try:
            messages = await self._store.get_messages_by_ids(
                session_id, region_info.message_ids
            )
            if not messages:
                logger.debug(
                    "Compression skipped: no messages found for region: session_id={}",
                    session_id,
                )
                return

            summary = await summarizer.summarize(messages)
            if not summary:
                logger.warning(
                    "Compression skipped: summary empty: session_id={}",
                    session_id,
                )
                return

            await self._store.replace_compressed_region(
                session_id, region_info.message_ids, summary
            )
            logger.info(
                "Compressed region replaced: session_id={}, messages={}",
                session_id,
                len(region_info.message_ids),
            )
        except Exception:
            logger.warning(
                "Summary and replace failed: session_id={}",
                session_id,
                exc_info=True,
            )

    async def _do_auto_archive(self, session_id: str) -> None:
        pass
