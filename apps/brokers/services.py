"""
Broker connection management services.

Provides utilities to get broker client instances from database connections,
handle credential decryption, and manage broker lifecycle.
"""
from typing import Optional
import logging

from .models import BrokerConnection
from .clients import AlpacaClient
from .clients.base import BrokerClient
from .encryption import decrypt_broker_credentials

logger = logging.getLogger(__name__)


def get_broker_client(broker_connection: BrokerConnection) -> BrokerClient:
    """
    Get broker client instance from a BrokerConnection model.

    Args:
        broker_connection: BrokerConnection instance

    Returns:
        Initialized broker client instance

    Raises:
        ValueError: If broker type is unsupported or credentials are invalid

    Example:
        >>> connection = BrokerConnection.objects.get(user=user, broker='alpaca')
        >>> client = get_broker_client(connection)
        >>> account = await client.get_account_info()
    """
    if not broker_connection.is_active:
        raise ValueError(f"Broker connection {broker_connection.id} is not active")

    # Decrypt credentials
    try:
        credentials = decrypt_broker_credentials(
            broker_connection.api_key_encrypted,
            broker_connection.api_secret_encrypted
        )
    except Exception as e:
        logger.error(f"Failed to decrypt credentials for connection {broker_connection.id}: {e}")
        raise ValueError(f"Invalid credentials for broker connection: {e}")

    api_key = credentials['api_key']
    api_secret = credentials['api_secret']

    # Get appropriate client based on broker type
    if broker_connection.broker in ['alpaca', 'alpaca_paper']:
        paper = broker_connection.broker == 'alpaca_paper'
        client = AlpacaClient(
            api_key=api_key,
            api_secret=api_secret,
            paper=paper
        )
        logger.info(f"Created Alpaca client for connection {broker_connection.id} (paper={paper})")
        return client

    # Add more brokers as implemented
    # elif broker_connection.broker == 'interactive_brokers':
    #     return IBKRClient(api_key=api_key, api_secret=api_secret)

    else:
        raise ValueError(f"Unsupported broker type: {broker_connection.broker}")


def get_active_broker_connection(user, broker: Optional[str] = None) -> Optional[BrokerConnection]:
    """
    Get user's active broker connection.

    Args:
        user: User instance
        broker: Optional broker type filter ('alpaca', 'alpaca_paper', etc.)

    Returns:
        Active BrokerConnection or None

    Example:
        >>> connection = get_active_broker_connection(user, broker='alpaca_paper')
        >>> if connection:
        >>>     client = get_broker_client(connection)
    """
    query = BrokerConnection.objects.filter(user=user, is_active=True)

    if broker:
        query = query.filter(broker=broker)

    return query.first()


def verify_broker_connection(broker_connection: BrokerConnection) -> dict:
    """
    Verify broker connection by attempting to fetch account info.

    Args:
        broker_connection: BrokerConnection instance

    Returns:
        Dictionary with verification results:
        - success: bool
        - message: str
        - account_info: dict (if successful)

    Example:
        >>> result = verify_broker_connection(connection)
        >>> if result['success']:
        >>>     print(f"Account value: {result['account_info']['portfolio_value']}")
    """
    try:
        client = get_broker_client(broker_connection)

        # Attempt to fetch account info
        import asyncio
        account_info = asyncio.run(client.get_account_info())

        # Update connection metadata
        broker_connection.metadata = broker_connection.metadata or {}
        broker_connection.metadata['last_verified'] = str(account_info.get('account_number', ''))
        broker_connection.metadata['last_verified_at'] = None  # Will be set by save
        broker_connection.save()

        logger.info(f"Verified broker connection {broker_connection.id}")

        return {
            'success': True,
            'message': 'Connection verified successfully',
            'account_info': account_info
        }

    except Exception as e:
        logger.error(f"Failed to verify broker connection {broker_connection.id}: {e}")
        return {
            'success': False,
            'message': str(e),
            'account_info': None
        }


async def async_verify_broker_connection(broker_connection: BrokerConnection) -> dict:
    """
    Async version of verify_broker_connection.

    Args:
        broker_connection: BrokerConnection instance

    Returns:
        Dictionary with verification results
    """
    try:
        client = get_broker_client(broker_connection)
        account_info = await client.get_account_info()

        # Update connection metadata
        broker_connection.metadata = broker_connection.metadata or {}
        broker_connection.metadata['last_verified'] = str(account_info.get('account_number', ''))
        broker_connection.save()

        logger.info(f"Verified broker connection {broker_connection.id}")

        return {
            'success': True,
            'message': 'Connection verified successfully',
            'account_info': account_info
        }

    except Exception as e:
        logger.error(f"Failed to verify broker connection {broker_connection.id}: {e}")
        return {
            'success': False,
            'message': str(e),
            'account_info': None
        }


def get_user_broker_clients(user) -> dict:
    """
    Get all active broker client instances for a user.

    Args:
        user: User instance

    Returns:
        Dictionary mapping broker type to client instance

    Example:
        >>> clients = get_user_broker_clients(user)
        >>> alpaca_client = clients.get('alpaca_paper')
        >>> if alpaca_client:
        >>>     positions = await alpaca_client.get_positions()
    """
    connections = BrokerConnection.objects.filter(user=user, is_active=True)
    clients = {}

    for connection in connections:
        try:
            client = get_broker_client(connection)
            clients[connection.broker] = client
        except Exception as e:
            logger.error(f"Failed to create client for connection {connection.id}: {e}")
            continue

    return clients


def close_broker_client(client: BrokerClient):
    """
    Close broker client and cleanup resources.

    Args:
        client: BrokerClient instance

    Example:
        >>> client = get_broker_client(connection)
        >>> try:
        >>>     # Use client...
        >>> finally:
        >>>     close_broker_client(client)
    """
    try:
        import asyncio
        asyncio.run(client.close())
        logger.info(f"Closed broker client: {client.get_broker_name()}")
    except Exception as e:
        logger.error(f"Error closing broker client: {e}")


# Context manager for broker clients
class BrokerClientContext:
    """
    Context manager for broker clients with automatic cleanup.

    Example:
        >>> async with BrokerClientContext(connection) as client:
        >>>     account = await client.get_account_info()
        >>>     positions = await client.get_positions()
    """

    def __init__(self, broker_connection: BrokerConnection):
        self.broker_connection = broker_connection
        self.client = None

    async def __aenter__(self):
        self.client = get_broker_client(self.broker_connection)
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.close()
        return False
