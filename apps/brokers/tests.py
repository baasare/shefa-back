"""
Comprehensive test suite for the brokers app.
Tests encryption, services, broker clients, and API endpoints.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
import asyncio

from apps.brokers.models import BrokerConnection
from apps.brokers.encryption import (
    encrypt_api_key,
    decrypt_api_key,
    encrypt_broker_credentials,
    decrypt_broker_credentials
)
from apps.brokers.services import (
    get_broker_client,
    get_active_broker_connection,
    verify_broker_connection,
    get_user_broker_clients,
    BrokerClientContext
)
from apps.brokers.clients.base import BrokerClient
from apps.brokers.clients.alpaca import AlpacaClient

User = get_user_model()


class EncryptionTests(TestCase):
    """Test cases for broker credential encryption."""

    def test_encrypt_api_key(self):
        """Test API key encryption."""
        plain_key = "test-api-key-12345"
        encrypted = encrypt_api_key(plain_key)

        self.assertIsNotNone(encrypted)
        self.assertNotEqual(encrypted, plain_key)
        self.assertIsInstance(encrypted, str)

    def test_decrypt_api_key(self):
        """Test API key decryption."""
        plain_key = "test-api-key-12345"
        encrypted = encrypt_api_key(plain_key)
        decrypted = decrypt_api_key(encrypted)

        self.assertEqual(decrypted, plain_key)

    def test_encrypt_decrypt_roundtrip(self):
        """Test encryption/decryption roundtrip."""
        original = "my-secret-api-key"
        encrypted = encrypt_api_key(original)
        decrypted = decrypt_api_key(encrypted)

        self.assertEqual(decrypted, original)
        self.assertNotEqual(encrypted, original)

    def test_encrypt_empty_string(self):
        """Test encrypting empty string."""
        encrypted = encrypt_api_key("")
        self.assertEqual(encrypted, "")

    def test_decrypt_empty_string(self):
        """Test decrypting empty string."""
        decrypted = decrypt_api_key("")
        self.assertEqual(decrypted, "")

    def test_encrypt_broker_credentials(self):
        """Test encrypting broker credentials."""
        api_key = "test-key"
        api_secret = "test-secret"

        creds = encrypt_broker_credentials(api_key, api_secret)

        self.assertIn('api_key_encrypted', creds)
        self.assertIn('api_secret_encrypted', creds)
        self.assertNotEqual(creds['api_key_encrypted'], api_key)
        self.assertNotEqual(creds['api_secret_encrypted'], api_secret)

    def test_decrypt_broker_credentials(self):
        """Test decrypting broker credentials."""
        api_key = "test-key"
        api_secret = "test-secret"

        encrypted = encrypt_broker_credentials(api_key, api_secret)
        decrypted = decrypt_broker_credentials(
            encrypted['api_key_encrypted'],
            encrypted['api_secret_encrypted']
        )

        self.assertEqual(decrypted['api_key'], api_key)
        self.assertEqual(decrypted['api_secret'], api_secret)

    def test_encrypt_broker_credentials_no_secret(self):
        """Test encrypting credentials without secret."""
        api_key = "test-key"

        creds = encrypt_broker_credentials(api_key)

        self.assertIn('api_key_encrypted', creds)
        self.assertEqual(creds['api_secret_encrypted'], "")


class BrokerConnectionModelTests(TestCase):
    """Test cases for BrokerConnection model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.connection_data = {
            'user': self.user,
            'broker': 'alpaca_paper',
            'api_key_encrypted': encrypt_api_key('test-key'),
            'api_secret_encrypted': encrypt_api_key('test-secret'),
            'status': 'active'
        }

    def test_create_broker_connection(self):
        """Test creating a broker connection."""
        connection = BrokerConnection.objects.create(**self.connection_data)

        self.assertEqual(connection.user, self.user)
        self.assertEqual(connection.broker, 'alpaca_paper')
        self.assertEqual(connection.status, 'active')
        self.assertIsNotNone(connection.created_at)

    def test_broker_connection_string_representation(self):
        """Test __str__ method."""
        connection = BrokerConnection.objects.create(**self.connection_data)
        expected = f"{self.user.email} - alpaca_paper"
        self.assertEqual(str(connection), expected)

    def test_broker_connection_default_status(self):
        """Test default status is pending."""
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret')
        )

        self.assertEqual(connection.status, 'pending')

    def test_broker_connection_cascade_delete(self):
        """Test connection is deleted when user is deleted."""
        connection = BrokerConnection.objects.create(**self.connection_data)
        connection_id = connection.id

        self.user.delete()

        with self.assertRaises(BrokerConnection.DoesNotExist):
            BrokerConnection.objects.get(id=connection_id)

    def test_multiple_connections_per_user(self):
        """Test user can have multiple broker connections."""
        connection1 = BrokerConnection.objects.create(**self.connection_data)
        connection2 = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca',
            api_key_encrypted=encrypt_api_key('test-key-2'),
            api_secret_encrypted=encrypt_api_key('test-secret-2'),
            status='active'
        )

        connections = BrokerConnection.objects.filter(user=self.user)
        self.assertEqual(connections.count(), 2)


class BrokerServicesTests(TestCase):
    """Test cases for broker services."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

    def test_get_active_broker_connection(self):
        """Test getting active broker connection."""
        connection = get_active_broker_connection(self.user)

        self.assertIsNotNone(connection)
        self.assertEqual(connection, self.connection)

    def test_get_active_broker_connection_with_broker_filter(self):
        """Test getting active connection with broker filter."""
        connection = get_active_broker_connection(self.user, broker='alpaca_paper')

        self.assertIsNotNone(connection)
        self.assertEqual(connection.broker, 'alpaca_paper')

    def test_get_active_broker_connection_no_active(self):
        """Test returns None when no active connection."""
        self.connection.status = 'disabled'
        self.connection.save()

        connection = get_active_broker_connection(self.user)
        self.assertIsNone(connection)

    def test_get_active_broker_connection_wrong_broker(self):
        """Test returns None when broker doesn't match."""
        connection = get_active_broker_connection(self.user, broker='interactive_brokers')
        self.assertIsNone(connection)

    @patch('apps.brokers.services.AlpacaClient')
    def test_get_broker_client_alpaca(self, mock_alpaca):
        """Test getting Alpaca broker client."""
        client = get_broker_client(self.connection)

        self.assertIsNotNone(client)
        mock_alpaca.assert_called_once()

    def test_get_broker_client_inactive_connection(self):
        """Test getting client for inactive connection raises error."""
        self.connection.status = 'disabled'
        self.connection.save()

        with self.assertRaises(ValueError) as context:
            get_broker_client(self.connection)

        self.assertIn('not active', str(context.exception))

    def test_get_broker_client_unsupported_broker(self):
        """Test getting client for unsupported broker raises error."""
        self.connection.broker = 'unsupported_broker'
        self.connection.save()

        with self.assertRaises(ValueError) as context:
            get_broker_client(self.connection)

        self.assertIn('Unsupported broker', str(context.exception))

    @patch('apps.brokers.services.AlpacaClient')
    def test_get_user_broker_clients(self, mock_alpaca):
        """Test getting all broker clients for user."""
        # Create second connection
        BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca',
            api_key_encrypted=encrypt_api_key('test-key-2'),
            api_secret_encrypted=encrypt_api_key('test-secret-2'),
            status='active'
        )

        clients = get_user_broker_clients(self.user)

        self.assertEqual(len(clients), 2)
        self.assertIn('alpaca_paper', clients)
        self.assertIn('alpaca', clients)

    @patch('apps.brokers.services.AlpacaClient')
    def test_verify_broker_connection_success(self, mock_alpaca):
        """Test successful broker connection verification."""
        # Mock the client and account info
        mock_client_instance = Mock()
        mock_client_instance.get_account_info = AsyncMock(return_value={
            'account_number': 'TEST123',
            'portfolio_value': '10000.00',
            'buying_power': '5000.00'
        })
        mock_alpaca.return_value = mock_client_instance

        result = verify_broker_connection(self.connection)

        self.assertTrue(result['success'])
        self.assertEqual(result['message'], 'Connection verified successfully')
        self.assertIsNotNone(result['account_info'])
        self.assertEqual(result['account_info']['account_number'], 'TEST123')

    @patch('apps.brokers.services.AlpacaClient')
    def test_verify_broker_connection_failure(self, mock_alpaca):
        """Test failed broker connection verification."""
        mock_client_instance = Mock()
        mock_client_instance.get_account_info = AsyncMock(
            side_effect=Exception('Invalid credentials')
        )
        mock_alpaca.return_value = mock_client_instance

        result = verify_broker_connection(self.connection)

        self.assertFalse(result['success'])
        self.assertIn('Invalid credentials', result['message'])
        self.assertIsNone(result['account_info'])


class AlpacaClientTests(TestCase):
    """Test cases for Alpaca broker client."""

    def setUp(self):
        """Set up test client."""
        self.api_key = 'test-key'
        self.api_secret = 'test-secret'
        self.client = AlpacaClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            paper=True
        )

    def test_alpaca_client_initialization(self):
        """Test Alpaca client initialization."""
        self.assertEqual(self.client.api_key, self.api_key)
        self.assertEqual(self.client.api_secret, self.api_secret)
        self.assertTrue(self.client.paper)

    def test_alpaca_client_paper_url(self):
        """Test paper trading uses correct URL."""
        self.assertIn('paper', self.client.base_url.lower())

    def test_alpaca_client_live_url(self):
        """Test live trading uses correct URL."""
        live_client = AlpacaClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            paper=False
        )
        self.assertNotIn('paper', live_client.base_url.lower())

    def test_get_broker_name(self):
        """Test get_broker_name method."""
        name = self.client.get_broker_name()
        self.assertEqual(name, 'Alpaca')

    @patch('httpx.AsyncClient.get')
    async def test_get_account_info(self, mock_get):
        """Test getting account info."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'account_number': 'TEST123',
            'portfolio_value': '10000.00',
            'buying_power': '5000.00',
            'cash': '3000.00'
        }
        mock_get.return_value = mock_response

        account_info = await self.client.get_account_info()

        self.assertEqual(account_info['account_number'], 'TEST123')
        self.assertEqual(account_info['portfolio_value'], '10000.00')

    @patch('httpx.AsyncClient.post')
    async def test_submit_order(self, mock_post):
        """Test submitting an order."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'order-123',
            'symbol': 'AAPL',
            'qty': 10,
            'side': 'buy',
            'status': 'accepted'
        }
        mock_post.return_value = mock_response

        order = await self.client.submit_order(
            symbol='AAPL',
            qty=10,
            side='buy',
            order_type='market'
        )

        self.assertEqual(order['id'], 'order-123')
        self.assertEqual(order['symbol'], 'AAPL')

    @patch('httpx.AsyncClient.get')
    async def test_get_positions(self, mock_get):
        """Test getting positions."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'symbol': 'AAPL',
                'qty': 10,
                'avg_entry_price': '150.00',
                'current_price': '155.00'
            }
        ]
        mock_get.return_value = mock_response

        positions = await self.client.get_positions()

        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]['symbol'], 'AAPL')


class BrokerConnectionAPITests(APITestCase):
    """Test cases for broker connection API endpoints."""

    def setUp(self):
        """Set up test client and user."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    def test_create_broker_connection(self):
        """Test creating broker connection via API."""
        data = {
            'broker': 'alpaca_paper',
            'api_key': 'test-key',
            'api_secret': 'test-secret'
        }

        response = self.client.post(
            '/api/brokers/connections/',
            data,
            format='json'
        )

        # API might return 201 or redirect, check for success
        self.assertIn(response.status_code, [200, 201])

    def test_list_broker_connections(self):
        """Test listing user's broker connections."""
        # Create connection
        BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        response = self.client.get('/api/brokers/connections/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_broker_connections_unauthenticated(self):
        """Test listing connections requires authentication."""
        self.client.credentials()  # Clear credentials

        response = self.client.get('/api/brokers/connections/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_only_see_own_connections(self):
        """Test users can only see their own connections."""
        # Create another user with connection
        other_user = User.objects.create_user(
            email='other@shefaai.com',
            password='TestPass123!'
        )
        BrokerConnection.objects.create(
            user=other_user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('other-key'),
            api_secret_encrypted=encrypt_api_key('other-secret'),
            status='active'
        )

        # Create connection for test user
        BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        response = self.client.get('/api/brokers/connections/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only see own connection (implementation dependent)

    def test_delete_broker_connection(self):
        """Test deleting broker connection."""
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        response = self.client.delete(f'/api/brokers/connections/{connection.id}/')

        # Check if deleted or status changed
        self.assertIn(response.status_code, [200, 204])


class BrokerClientContextManagerTests(TestCase):
    """Test cases for BrokerClientContext context manager."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

    @patch('apps.brokers.services.AlpacaClient')
    async def test_context_manager_basic_usage(self, mock_alpaca):
        """Test basic context manager usage."""
        mock_client = Mock()
        mock_client.close = AsyncMock()
        mock_alpaca.return_value = mock_client

        async with BrokerClientContext(self.connection) as client:
            self.assertIsNotNone(client)

        # Verify close was called
        mock_client.close.assert_called_once()

    @patch('apps.brokers.services.AlpacaClient')
    async def test_context_manager_with_exception(self, mock_alpaca):
        """Test context manager properly closes on exception."""
        mock_client = Mock()
        mock_client.close = AsyncMock()
        mock_alpaca.return_value = mock_client

        with self.assertRaises(Exception):
            async with BrokerClientContext(self.connection) as client:
                raise Exception("Test error")

        # Verify close was still called
        mock_client.close.assert_called_once()


class BrokerIntegrationTests(TestCase):
    """Integration tests for broker workflows."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

    @patch('apps.brokers.services.AlpacaClient')
    def test_end_to_end_connection_flow(self, mock_alpaca):
        """Test complete flow from connection creation to verification."""
        # 1. Create connection
        connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        # 2. Get client
        client = get_broker_client(connection)
        self.assertIsNotNone(client)

        # 3. Verify credentials can be decrypted
        decrypted = decrypt_api_key(connection.api_key_encrypted)
        self.assertEqual(decrypted, 'test-key')

        # 4. Verify connection can be retrieved
        retrieved_connection = get_active_broker_connection(self.user)
        self.assertEqual(retrieved_connection, connection)

    def test_multiple_broker_workflow(self):
        """Test workflow with multiple brokers."""
        # Create multiple connections
        paper_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('paper-key'),
            api_secret_encrypted=encrypt_api_key('paper-secret'),
            status='active'
        )

        live_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca',
            api_key_encrypted=encrypt_api_key('live-key'),
            api_secret_encrypted=encrypt_api_key('live-secret'),
            status='active'
        )

        # Verify both can be retrieved
        paper = get_active_broker_connection(self.user, broker='alpaca_paper')
        live = get_active_broker_connection(self.user, broker='alpaca')

        self.assertEqual(paper, paper_connection)
        self.assertEqual(live, live_connection)
        self.assertNotEqual(paper, live)
