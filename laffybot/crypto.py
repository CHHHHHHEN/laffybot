"""Fernet-based encryption for API key storage."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from laffybot_agent_runtime.providers.errors import ProviderConfigError
from loguru import logger

ENCRYPTION_KEY_ENV_VAR = "LAFFYBOT_ENCRYPTION_KEY"
ENV_FILE_NAME = ".env"


def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return current.parent


def _get_env_file_path() -> Path:
    return _find_project_root() / ENV_FILE_NAME


def _generate_fernet_key() -> str:
    return Fernet.generate_key().decode()


def _load_env_file() -> dict[str, str]:
    env_file = _get_env_file_path()
    env_vars: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def _save_env_file(env_vars: dict[str, str]) -> None:
    env_file = _get_env_file_path()
    lines = []
    for key, value in env_vars.items():
        lines.append(f"{key}={value}")
    env_file.write_text("\n".join(lines) + "\n")
    logger.info("Saved encryption key to {}", env_file)


def _load_or_generate_key() -> str:
    key = os.environ.get(ENCRYPTION_KEY_ENV_VAR)
    if key:
        return key

    env_vars = _load_env_file()
    key = env_vars.get(ENCRYPTION_KEY_ENV_VAR)

    if not key:
        key = _generate_fernet_key()
        env_vars[ENCRYPTION_KEY_ENV_VAR] = key
        _save_env_file(env_vars)
        logger.info("Generated new encryption key")
    else:
        logger.debug("Loaded encryption key from .env file")

    os.environ[ENCRYPTION_KEY_ENV_VAR] = key
    return key


def _get_fernet() -> Fernet:
    key = _load_or_generate_key()
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        logger.error("Invalid encryption key format: {}", exc)
        raise ProviderConfigError(f"Invalid encryption key format: {exc}") from exc


def encrypt_api_key(plaintext: str) -> str:
    if not plaintext:
        raise ProviderConfigError("Cannot encrypt empty API key")
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    if not ciphertext:
        raise ProviderConfigError("Cannot decrypt empty ciphertext")
    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        logger.error("API key decryption failed: invalid token or key")
        raise ProviderConfigError(
            "API key decryption failed: invalid token or key"
        ) from exc
    except Exception as exc:
        logger.error("API key decryption failed: {}", exc)
        raise ProviderConfigError(f"API key decryption failed: {exc}") from exc


def validate_encryption_key() -> None:
    key = _load_or_generate_key()
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        raise ProviderConfigError(f"Invalid encryption key format: {exc}") from exc
