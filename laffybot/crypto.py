"""Fernet-based encryption for API key storage."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from laffybot.providers.errors import ProviderConfigError

ENCRYPTION_KEY_ENV_VAR = "LAFFYBOT_ENCRYPTION_KEY"


def _get_fernet() -> Fernet:
    key = os.environ.get(ENCRYPTION_KEY_ENV_VAR)
    if not key:
        logger.error("Encryption key not set: {}", ENCRYPTION_KEY_ENV_VAR)
        raise ProviderConfigError(
            f"Encryption key not set: set {ENCRYPTION_KEY_ENV_VAR} environment variable"
        )
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
        raise ProviderConfigError("API key decryption failed: invalid token or key") from exc
    except Exception as exc:
        logger.error("API key decryption failed: {}", exc)
        raise ProviderConfigError(f"API key decryption failed: {exc}") from exc


def validate_encryption_key() -> None:
    key = os.environ.get(ENCRYPTION_KEY_ENV_VAR)
    if not key:
        raise ProviderConfigError(
            f"Encryption key not set: set {ENCRYPTION_KEY_ENV_VAR} environment variable"
        )
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        raise ProviderConfigError(f"Invalid encryption key format: {exc}") from exc
