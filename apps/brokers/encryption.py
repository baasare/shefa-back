"""
API key encryption utilities for secure storage of broker credentials.

Uses Fernet symmetric encryption from cryptography library.
"""
from cryptography.fernet import Fernet
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def get_encryption_key():
    """
    Get encryption key from settings.

    Returns:
        bytes: Encryption key

    Raises:
        ValueError: If ENCRYPTION_KEY not configured
    """
    key = getattr(settings, 'ENCRYPTION_KEY', None)

    if not key:
        raise ValueError(
            "ENCRYPTION_KEY not configured in settings. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )

    # Convert string to bytes if needed
    if isinstance(key, str):
        key = key.encode()

    return key


def generate_encryption_key():
    """
    Generate a new Fernet encryption key.

    Returns:
        str: Base64-encoded encryption key
    """
    key = Fernet.generate_key()
    return key.decode()


def encrypt_api_key(plain_key: str) -> str:
    """
    Encrypt an API key for secure storage.

    Args:
        plain_key: Plain text API key

    Returns:
        Encrypted API key (base64 encoded string)

    Example:
        >>> encrypted = encrypt_api_key("my-secret-api-key")
        >>> print(encrypted)
        'gAAAAABf...'
    """
    if not plain_key:
        return ""

    try:
        cipher = Fernet(get_encryption_key())
        encrypted = cipher.encrypt(plain_key.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Error encrypting API key: {e}")
        raise


def decrypt_api_key(encrypted_key: str) -> str:
    """
    Decrypt an API key for use.

    Args:
        encrypted_key: Encrypted API key (base64 encoded string)

    Returns:
        Plain text API key

    Example:
        >>> decrypted = decrypt_api_key('gAAAAABf...')
        >>> print(decrypted)
        'my-secret-api-key'
    """
    if not encrypted_key:
        return ""

    try:
        cipher = Fernet(get_encryption_key())
        decrypted = cipher.decrypt(encrypted_key.encode())
        return decrypted.decode()
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


def validate_encryption_key():
    """
    Validate that encryption key is properly configured.

    Returns:
        bool: True if key is valid

    Raises:
        ValueError: If key is invalid
    """
    try:
        key = get_encryption_key()

        # Try to create a Fernet instance
        cipher = Fernet(key)

        # Test encryption/decryption
        test_data = "test"
        encrypted = cipher.encrypt(test_data.encode())
        decrypted = cipher.decrypt(encrypted).decode()

        if decrypted != test_data:
            raise ValueError("Encryption key validation failed")

        logger.info("Encryption key validated successfully")
        return True

    except Exception as e:
        logger.error(f"Encryption key validation failed: {e}")
        raise ValueError(f"Invalid encryption key: {e}")


# Validate on module import (optional - comment out if causing issues)
try:
    if hasattr(settings, 'ENCRYPTION_KEY') and settings.ENCRYPTION_KEY:
        validate_encryption_key()
except Exception as e:
    logger.warning(f"Encryption key validation skipped: {e}")
