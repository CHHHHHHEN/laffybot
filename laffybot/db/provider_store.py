"""SQLite-backed persistence for providers, models, and active selection."""

from __future__ import annotations

import json
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiosqlite
from loguru import logger

from laffybot.crypto import decrypt_api_key, encrypt_api_key
from laffybot.db.base import BaseStore
from laffybot.db.manager import DatabaseManager


# Local exceptions — no dependency on agent-runtime
class ProviderNotFoundError(Exception):
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"Provider '{provider_id}' not found")


class ModelNotFoundError(Exception):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        super().__init__(f"Model '{model_name}' not found")


class ModelNameConflictError(Exception):
    def __init__(self, name: str, provider_id: str) -> None:
        self.name = name
        self.provider_id = provider_id
        super().__init__(
            f"Model name '{name}' already exists for provider '{provider_id}'"
        )


# Local ProviderConfig DTO — pure data, no agent-runtime dependency
@dataclass
class ProviderConfig:
    provider_id: str
    name: str
    api_key: str
    base_url: str
    extra_headers: dict[str, str] | None = None
    extra_body: dict[str, Any] | None = None


_PROVIDER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS providers (
    provider_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    api_key_encrypted TEXT,
    extra_headers TEXT NOT NULL DEFAULT '{}',
    extra_body TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_models (
    model_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL REFERENCES providers(provider_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE(provider_id, name)
);

"""


@dataclass
class ProviderRow:
    provider_id: str
    name: str
    base_url: str
    has_api_key: bool
    extra_headers: dict[str, str]
    extra_body: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class ModelRow:
    model_id: str
    provider_id: str
    name: str


class ProviderStore(BaseStore):
    @abstractmethod
    async def create_provider(
        self,
        name: str,
        base_url: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> ProviderRow:
        raise NotImplementedError

    @abstractmethod
    async def get_provider(self, provider_id: str) -> ProviderRow:
        raise NotImplementedError

    @abstractmethod
    async def update_provider(
        self,
        provider_id: str,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> ProviderRow:
        raise NotImplementedError

    @abstractmethod
    async def delete_provider(self, provider_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_providers(self) -> list[ProviderRow]:
        raise NotImplementedError

    @abstractmethod
    async def add_model(self, provider_id: str, name: str) -> ModelRow:
        raise NotImplementedError

    @abstractmethod
    async def delete_model(self, model_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_models(self, provider_id: str) -> list[ModelRow]:
        raise NotImplementedError

    @abstractmethod
    async def get_provider_config(self, provider_id: str) -> ProviderConfig:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class SQLiteProviderStore(ProviderStore):
    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db_manager = db_manager
        db_manager.add_schema(_PROVIDER_SCHEMA_SQL)

    async def create_provider(
        self,
        name: str,
        base_url: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> ProviderRow:
        db = await self._db_manager.connect()
        now = DatabaseManager.now()
        timestamp = DatabaseManager.format_dt(now)
        provider_id = name.lower().replace(" ", "_")
        encrypted_key = encrypt_api_key(api_key) if api_key else None
        headers_json = json.dumps(extra_headers or {}, ensure_ascii=False)
        body_json = json.dumps(extra_body or {}, ensure_ascii=False)

        await db.execute(
            """
            INSERT INTO providers (provider_id, name, base_url, api_key_encrypted,
                                   extra_headers, extra_body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                name,
                base_url,
                encrypted_key,
                headers_json,
                body_json,
                timestamp,
                timestamp,
            ),
        )
        await db.commit()
        return ProviderRow(
            provider_id=provider_id,
            name=name,
            base_url=base_url,
            has_api_key=bool(api_key),
            extra_headers=extra_headers or {},
            extra_body=extra_body or {},
            created_at=now,
            updated_at=now,
        )

    async def get_provider(self, provider_id: str) -> ProviderRow:
        db = await self._db_manager.connect()
        async with db.execute(
            "SELECT * FROM providers WHERE provider_id = ?",
            (provider_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ProviderNotFoundError(provider_id)
        return self._row_to_provider(row)

    async def update_provider(
        self,
        provider_id: str,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> ProviderRow:
        db = await self._db_manager.connect()
        now = DatabaseManager.format_dt(DatabaseManager.now())

        fields: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]

        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if base_url is not None:
            fields.append("base_url = ?")
            params.append(base_url)
        if api_key:
            fields.append("api_key_encrypted = ?")
            params.append(encrypt_api_key(api_key))
        if extra_headers is not None:
            fields.append("extra_headers = ?")
            params.append(json.dumps(extra_headers, ensure_ascii=False))
        if extra_body is not None:
            fields.append("extra_body = ?")
            params.append(json.dumps(extra_body, ensure_ascii=False))

        params.append(provider_id)
        sql = f"UPDATE providers SET {', '.join(fields)} WHERE provider_id = ?"
        cursor = await db.execute(sql, params)
        await db.commit()
        if cursor.rowcount == 0:
            raise ProviderNotFoundError(provider_id)
        return await self.get_provider(provider_id)

    async def delete_provider(self, provider_id: str) -> None:
        db = await self._db_manager.connect()
        cursor = await db.execute(
            "DELETE FROM providers WHERE provider_id = ?",
            (provider_id,),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise ProviderNotFoundError(provider_id)

    async def list_providers(self) -> list[ProviderRow]:
        db = await self._db_manager.connect()
        async with db.execute(
            "SELECT * FROM providers ORDER BY created_at ASC",
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_provider(row) for row in rows]

    async def add_model(self, provider_id: str, name: str) -> ModelRow:
        db = await self._db_manager.connect()
        # Verify provider exists
        await self.get_provider(provider_id)
        # Check for duplicate name under same provider
        async with db.execute(
            "SELECT model_id FROM provider_models WHERE provider_id = ? AND name = ?",
            (provider_id, name),
        ) as cursor:
            existing = await cursor.fetchone()
        if existing is not None:
            raise ModelNameConflictError(name, provider_id)

        model_id = f"m_{provider_id}_{name.lower().replace('/', '_').replace(' ', '_')}"
        await db.execute(
            "INSERT INTO provider_models (model_id, provider_id, name) VALUES (?, ?, ?)",
            (model_id, provider_id, name),
        )
        await db.commit()
        return ModelRow(model_id=model_id, provider_id=provider_id, name=name)

    async def delete_model(self, model_id: str) -> None:
        db = await self._db_manager.connect()
        # Look up model name before deleting (for error reporting)
        async with db.execute(
            "SELECT name FROM provider_models WHERE model_id = ?",
            (model_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise ModelNotFoundError(f"id:{model_id}")
        model_name: str = row["name"]

        cursor = await db.execute(
            "DELETE FROM provider_models WHERE model_id = ?",
            (model_id,),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise ModelNotFoundError(model_name)

    async def list_models(self, provider_id: str) -> list[ModelRow]:
        db = await self._db_manager.connect()
        # Verify provider exists
        await self.get_provider(provider_id)
        async with db.execute(
            "SELECT model_id, provider_id, name FROM provider_models WHERE provider_id = ? ORDER BY name ASC",
            (provider_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            ModelRow(
                model_id=row["model_id"],
                provider_id=row["provider_id"],
                name=row["name"],
            )
            for row in rows
        ]

    async def get_provider_config(self, provider_id: str) -> ProviderConfig:
        provider = await self.get_provider(provider_id)
        api_key_plain = ""
        if provider.has_api_key:
            db = await self._db_manager.connect()
            async with db.execute(
                "SELECT api_key_encrypted FROM providers WHERE provider_id = ?",
                (provider_id,),
            ) as cursor:
                row = await cursor.fetchone()
            encrypted = row["api_key_encrypted"] if row is not None else None
            if encrypted:
                try:
                    api_key_plain = decrypt_api_key(encrypted)
                except Exception as exc:
                    logger.error(
                        "Failed to decrypt API key for provider_id={}: {}",
                        provider_id,
                        exc,
                    )
                    raise
        logger.debug("Retrieved provider config: provider_id={}", provider_id)
        return ProviderConfig(
            provider_id=provider.provider_id,
            name=provider.name,
            api_key=api_key_plain,
            base_url=provider.base_url,
            extra_headers=provider.extra_headers,
            extra_body=provider.extra_body,
        )

    async def close(self) -> None:
        pass

    def _row_to_provider(self, row: aiosqlite.Row) -> ProviderRow:
        return ProviderRow(
            provider_id=row["provider_id"],
            name=row["name"],
            base_url=row["base_url"],
            has_api_key=bool(row["api_key_encrypted"]),
            extra_headers=json.loads(row["extra_headers"])
            if isinstance(row["extra_headers"], str)
            else (row["extra_headers"] or {}),
            extra_body=json.loads(row["extra_body"])
            if isinstance(row["extra_body"], str)
            else (row["extra_body"] or {}),
            created_at=DatabaseManager.parse_dt(row["created_at"]),
            updated_at=DatabaseManager.parse_dt(row["updated_at"]),
        )
