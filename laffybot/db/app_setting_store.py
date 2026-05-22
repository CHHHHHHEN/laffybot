"""Global app settings store (key-value pairs with typed methods)."""

from __future__ import annotations

import json
from abc import abstractmethod
from dataclasses import dataclass

from loguru import logger

from laffybot.db.base import BaseStore
from laffybot.db.manager import DatabaseManager

_APP_SETTINGS_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(slots=True)
class ProviderModelPair:
    provider_id: str
    model_name: str


class AppSettingStore(BaseStore):
    @abstractmethod
    async def get_default_session_config(self) -> ProviderModelPair | None:
        raise NotImplementedError

    @abstractmethod
    async def set_default_session_config(
        self, provider_id: str, model_name: str
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_default_session_config(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_summary_model(self) -> ProviderModelPair | None:
        raise NotImplementedError

    @abstractmethod
    async def set_summary_model(self, provider_id: str, model_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_summary_model(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_extract_model(self) -> ProviderModelPair | None:
        raise NotImplementedError

    @abstractmethod
    async def set_extract_model(self, provider_id: str, model_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_extract_model(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_consolidation_model(self) -> ProviderModelPair | None:
        raise NotImplementedError

    @abstractmethod
    async def set_consolidation_model(self, provider_id: str, model_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_consolidation_model(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_system_prompt(self) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def set_system_prompt(self, prompt: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_skills_path(self) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def set_skills_path(self, path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_enabled_skills(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def set_enabled_skills(self, skills: list[str]) -> None:
        """Set the list of enabled skill names."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the store, releasing resources."""
        raise NotImplementedError


class SQLiteAppSettingStore(AppSettingStore):
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db_manager = db_manager
        db_manager.add_schema(_APP_SETTINGS_SCHEMA_SQL)

    async def _get_raw(self, key: str) -> str | None:
        db = await self._db_manager.connect()
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        val: str = row["value"]
        return val

    async def _set_raw(self, key: str, value: str) -> None:
        db = await self._db_manager.connect()
        await db.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()

    async def _get(self, key: str) -> ProviderModelPair | None:
        raw = await self._get_raw(key)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return ProviderModelPair(
                provider_id=data["provider_id"],
                model_name=data["model_name"],
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Invalid value for app setting key={}", key)
            return None

    async def _set(self, key: str, provider_id: str, model_name: str) -> None:
        value = json.dumps(
            {"provider_id": provider_id, "model_name": model_name}, ensure_ascii=False
        )
        await self._set_raw(key, value)

    async def _delete(self, key: str) -> None:
        db = await self._db_manager.connect()
        await db.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        await db.commit()

    async def get_default_session_config(self) -> ProviderModelPair | None:
        return await self._get("default_session_config")

    async def set_default_session_config(
        self, provider_id: str, model_name: str
    ) -> None:
        await self._set("default_session_config", provider_id, model_name)

    async def delete_default_session_config(self) -> None:
        await self._delete("default_session_config")

    async def get_summary_model(self) -> ProviderModelPair | None:
        return await self._get("summary_model")

    async def set_summary_model(self, provider_id: str, model_name: str) -> None:
        await self._set("summary_model", provider_id, model_name)

    async def delete_summary_model(self) -> None:
        await self._delete("summary_model")

    async def get_extract_model(self) -> ProviderModelPair | None:
        return await self._get("extract_model")

    async def set_extract_model(self, provider_id: str, model_name: str) -> None:
        await self._set("extract_model", provider_id, model_name)

    async def delete_extract_model(self) -> None:
        await self._delete("extract_model")

    async def get_consolidation_model(self) -> ProviderModelPair | None:
        return await self._get("consolidation_model")

    async def set_consolidation_model(self, provider_id: str, model_name: str) -> None:
        await self._set("consolidation_model", provider_id, model_name)

    async def delete_consolidation_model(self) -> None:
        await self._delete("consolidation_model")

    async def get_system_prompt(self) -> str | None:
        return await self._get_raw("system_prompt")

    async def set_system_prompt(self, prompt: str) -> None:
        await self._set_raw("system_prompt", prompt)

    async def get_skills_path(self) -> str | None:
        return await self._get_raw("skills_path")

    async def set_skills_path(self, path: str) -> None:
        await self._set_raw("skills_path", path)

    async def get_enabled_skills(self) -> list[str]:
        raw = await self._get_raw("enabled_skills")
        if raw is None:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    async def set_enabled_skills(self, skills: list[str]) -> None:
        await self._set_raw("enabled_skills", json.dumps(skills, ensure_ascii=False))

    async def close(self) -> None:
        pass
