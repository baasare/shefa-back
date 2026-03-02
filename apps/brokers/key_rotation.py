"""
Encryption key rotation system for secure credential management.

Allows rotating encryption keys without downtime by supporting multiple keys.
"""
from typing import List, Optional
from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.management.base import BaseCommand
import os
import logging

logger = logging.getLogger(__name__)


class KeyRotationManager:
    """
    Manages encryption key rotation with zero downtime.

    Uses MultiFernet to support multiple keys during rotation period.
    """

    def __init__(self):
        """Initialize with keys from settings."""
        self.keys = self._load_keys()
        self.fernet = MultiFernet([Fernet(key.encode()) for key in self.keys])

    def _load_keys(self) -> List[str]:
        """
        Load encryption keys from environment.

        Keys should be in format:
        ENCRYPTION_KEY=primary_key
        ENCRYPTION_KEY_OLD_1=old_key_1
        ENCRYPTION_KEY_OLD_2=old_key_2
        """
        keys = []

        # Primary key (required)
        primary_key = os.environ.get('ENCRYPTION_KEY')
        if not primary_key:
            raise ValueError("ENCRYPTION_KEY environment variable is required")
        keys.append(primary_key)

        # Old keys (optional, for rotation)
        for i in range(1, 6):  # Support up to 5 old keys
            old_key = os.environ.get(f'ENCRYPTION_KEY_OLD_{i}')
            if old_key:
                keys.append(old_key)

        logger.info(f"Loaded {len(keys)} encryption keys")
        return keys

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt with primary key.

        Args:
            plaintext: Plain text to encrypt

        Returns:
            Encrypted text
        """
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt with any available key.

        MultiFernet automatically tries all keys until one works.

        Args:
            ciphertext: Encrypted text

        Returns:
            Decrypted plain text
        """
        return self.fernet.decrypt(ciphertext.encode()).decode()

    def rotate_ciphertext(self, ciphertext: str) -> str:
        """
        Re-encrypt ciphertext with primary key.

        Use this to migrate data encrypted with old keys to new key.

        Args:
            ciphertext: Text encrypted with old key

        Returns:
            Text re-encrypted with primary key
        """
        # Decrypt with any available key
        plaintext = self.decrypt(ciphertext)

        # Re-encrypt with primary key only
        primary_fernet = Fernet(self.keys[0].encode())
        return primary_fernet.encrypt(plaintext.encode()).decode()


# Singleton instance
_key_manager = None

def get_key_manager() -> KeyRotationManager:
    """Get singleton KeyRotationManager instance."""
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyRotationManager()
    return _key_manager


def rotate_broker_credentials():
    """
    Rotate all broker credentials to use new primary key.

    Run this management command after adding a new primary key.
    """
    from apps.brokers.models import BrokerConnection

    manager = get_key_manager()
    connections = BrokerConnection.objects.all()

    logger.info(f"Starting rotation for {connections.count()} broker connections")

    rotated_count = 0
    error_count = 0

    for connection in connections:
        try:
            # Rotate API key
            if connection.api_key_encrypted:
                connection.api_key_encrypted = manager.rotate_ciphertext(
                    connection.api_key_encrypted
                )

            # Rotate API secret
            if connection.api_secret_encrypted:
                connection.api_secret_encrypted = manager.rotate_ciphertext(
                    connection.api_secret_encrypted
                )

            connection.save()
            rotated_count += 1

            if rotated_count % 100 == 0:
                logger.info(f"Rotated {rotated_count} connections...")

        except Exception as e:
            logger.error(f"Error rotating connection {connection.id}: {e}")
            error_count += 1

    logger.info(f"Rotation complete: {rotated_count} success, {error_count} errors")
    return rotated_count, error_count


# Update encryption.py to use KeyRotationManager
def encrypt_broker_credentials(api_key: str, api_secret: str) -> tuple:
    """
    Encrypt broker credentials.

    Args:
        api_key: Plain API key
        api_secret: Plain API secret

    Returns:
        Tuple of (encrypted_key, encrypted_secret)
    """
    manager = get_key_manager()
    return (
        manager.encrypt(api_key),
        manager.encrypt(api_secret)
    )


def decrypt_broker_credentials(
    encrypted_key: str,
    encrypted_secret: str
) -> dict:
    """
    Decrypt broker credentials.

    Args:
        encrypted_key: Encrypted API key
        encrypted_secret: Encrypted API secret

    Returns:
        Dictionary with decrypted credentials
    """
    manager = get_key_manager()
    return {
        'api_key': manager.decrypt(encrypted_key),
        'api_secret': manager.decrypt(encrypted_secret)
    }


def generate_new_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        Base64-encoded encryption key
    """
    return Fernet.generate_key().decode()


# Management command for key rotation
class Command(BaseCommand):
    """
    Django management command to rotate encryption keys.

    Usage:
        # Generate new key
        python manage.py rotate_keys --generate

        # Rotate existing credentials to new key
        python manage.py rotate_keys --rotate
    """
    help = 'Manage encryption key rotation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--generate',
            action='store_true',
            help='Generate a new encryption key'
        )
        parser.add_argument(
            '--rotate',
            action='store_true',
            help='Rotate all credentials to new primary key'
        )

    def handle(self, *args, **options):
        if options['generate']:
            new_key = generate_new_key()
            self.stdout.write(self.style.SUCCESS(
                f"\nNew encryption key generated:\n{new_key}\n"
            ))
            self.stdout.write(self.style.WARNING(
                "\nTo rotate keys:\n"
                "1. Set ENCRYPTION_KEY_OLD_1 to current ENCRYPTION_KEY in .env\n"
                "2. Set ENCRYPTION_KEY to new key above in .env\n"
                "3. Restart application\n"
                "4. Run: python manage.py rotate_keys --rotate\n"
                "5. After 24 hours, remove ENCRYPTION_KEY_OLD_1 from .env\n"
            ))

        elif options['rotate']:
            self.stdout.write("Starting key rotation...")
            rotated, errors = rotate_broker_credentials()

            if errors == 0:
                self.stdout.write(self.style.SUCCESS(
                    f"Successfully rotated {rotated} broker connections"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"Rotation completed with {errors} errors. "
                    f"{rotated} connections rotated successfully."
                ))

        else:
            self.stdout.write(self.style.ERROR(
                "Please specify --generate or --rotate"
            ))
