"""
API key encryption utilities for secure storage of broker credentials.

Uses Fernet symmetric encryption with multi-key rotation support.
"""

import logging
from apps.brokers.key_rotation import get_key_manager

logger = logging.getLogger(__name__)


def encrypt_api_key(plain_key: str) -> str:
    """
    Encrypt an API key for secure storage.

    Uses key rotation manager for production deployments.

    Args:
        plain_key: Plain text API key

    Returns:
        Encrypted API key (base64 encoded string)

    Example:
        >>> manager_instance = get_key_manager()
        >>> encrypted = manager_instance.encrypt("my-secret-api-key")
        >>> print(encrypted)
        'gAAAAABf...'
    """
    if not plain_key:
        return ""

    try:
        manager = get_key_manager()
        return manager.encrypt(plain_key)

    except Exception as e:
        logger.error(f"Error encrypting API key: {e}")
        raise


def decrypt_api_key(encrypted_key: str) -> str:
    """
    Decrypt an API key for use.

    Uses key rotation manager to support decryption with old keys.

    Args:
        encrypted_key: Encrypted API key (base64 encoded string)

    Returns:
        Plain text API key

    Example:
        >>> manager_instance = get_key_manager()
        >>> encrypted = manager_instance.decrypt('gAAAAABf...')
        >>> print(decrypted)
        'my-secret-api-key'
    """
    if not encrypted_key:
        return ""

    try:
        manager = get_key_manager()
        return manager.decrypt(encrypted_key)

    except Exception as e:
        logger.error(f"Error decrypting API key: {e}")
        raise


def encrypt_broker_credentials(api_key: str, api_secret: str = "") -> dict:
    """
    Encrypt broker API credentials.

    Args:
        api_key: Broker API key
        api_secret: Broker API secret (optional)

    Returns:
        Dictionary with encrypted credentials

    Example:
        >>> creds = encrypt_broker_credentials("key123", "secret456")
        >>> print(creds)
        {'api_key_encrypted': 'gAAA...', 'api_secret_encrypted': 'gAAA...'}
    """
    return {
        'api_key_encrypted': encrypt_api_key(api_key),
        'api_secret_encrypted': encrypt_api_key(api_secret) if api_secret else ""
    }


def decrypt_broker_credentials(api_key_encrypted: str, api_secret_encrypted: str = "") -> dict:
    """
    Decrypt broker API credentials.

    Args:
        api_key_encrypted: Encrypted API key
        api_secret_encrypted: Encrypted API secret (optional)

    Returns:
        Dictionary with decrypted credentials

    Example:
        >>> creds = decrypt_broker_credentials('gAAA...', 'gAAA...')
        >>> print(creds)
        {'api_key': 'key123', 'api_secret': 'secret456'}
    """
    return {
        'api_key': decrypt_api_key(api_key_encrypted),
        'api_secret': decrypt_api_key(api_secret_encrypted) if api_secret_encrypted else ""
    }
