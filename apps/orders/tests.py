"""
Comprehensive test suite for the orders app.
Tests order execution, services, tasks, and API endpoints.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal
from datetime import timedelta
import asyncio

from apps.orders.models import Order, Trade
from apps.orders.execution import OrderExecutor
from apps.orders.services import (
    calculate_position_size,
    validate_order,
    check_buying_power,
    requires_approval,
    create_trade_from_order
)
from apps.portfolios.models import Portfolio, Position
from apps.brokers.models import BrokerConnection
from apps.brokers.encryption import encrypt_api_key

User = get_user_model()


class OrderModelTests(TestCase):
    """Test cases for Order model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            approval_threshold=Decimal('500.00')
        )

        self.broker_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

    def test_create_order(self):
        """Test creating an order."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market',
            status='pending'
        )

        self.assertEqual(order.portfolio, self.portfolio)
        self.assertEqual(order.symbol, 'AAPL')
        self.assertEqual(order.quantity, 10)
        self.assertEqual(order.side, 'buy')
        self.assertEqual(order.status, 'pending')

    def test_order_string_representation(self):
        """Test __str__ method."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market'
        )

        expected = f"BUY 10 AAPL (market)"
        self.assertEqual(str(order), expected)

    def test_order_default_status(self):
        """Test default status is pending."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market'
        )

        self.assertEqual(order.status, 'pending')

    def test_order_estimated_cost(self):
        """Test estimated_cost calculation."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='limit',
            limit_price=Decimal('150.00')
        )

        expected_cost = Decimal('1500.00')
        self.assertEqual(order.estimated_cost, expected_cost)

    def test_order_estimated_cost_market_order(self):
        """Test estimated_cost for market order."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market'
        )

        # Market order without estimated price should be None
        self.assertIsNone(order.estimated_cost)

    def test_order_cascade_delete_with_portfolio(self):
        """Test order is deleted when portfolio is deleted."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market'
        )
        order_id = order.id

        self.portfolio.delete()

        with self.assertRaises(Order.DoesNotExist):
            Order.objects.get(id=order_id)

    def test_approval_required_flag(self):
        """Test approval_required flag."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market',
            approval_required=True,
            status='pending_approval'
        )

        self.assertTrue(order.approval_required)
        self.assertEqual(order.status, 'pending_approval')


class TradeModelTests(TestCase):
    """Test cases for Trade model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.broker_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        self.order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market'
        )

    def test_create_trade(self):
        """Test creating a trade."""
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            order=self.order,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00')
        )

        self.assertEqual(trade.portfolio, self.portfolio)
        self.assertEqual(trade.order, self.order)
        self.assertEqual(trade.symbol, 'AAPL')
        self.assertEqual(trade.quantity, 10)
        self.assertEqual(trade.side, 'buy')
        self.assertEqual(trade.price, Decimal('150.00'))

    def test_trade_total_value(self):
        """Test total_value calculation."""
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            order=self.order,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00')
        )

        expected_value = Decimal('1500.00')
        self.assertEqual(trade.total_value, expected_value)

    def test_trade_with_commission(self):
        """Test trade with commission."""
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            order=self.order,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00'),
            commission=Decimal('1.00')
        )

        self.assertEqual(trade.commission, Decimal('1.00'))
        self.assertEqual(trade.total_value, Decimal('1500.00'))

    def test_trade_string_representation(self):
        """Test __str__ method."""
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            order=self.order,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00')
        )

        expected = f"BUY 10 AAPL @ $150.00"
        self.assertEqual(str(trade), expected)

    def test_trade_without_order(self):
        """Test trade can be created without order (manual trade)."""
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00')
        )

        self.assertIsNone(trade.order)
        self.assertEqual(trade.symbol, 'AAPL')


class OrderServicesTests(TestCase):
    """Test cases for order services."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            approval_threshold=Decimal('500.00')
        )

        self.broker_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

    def test_calculate_position_size_fixed(self):
        """Test fixed position size calculation."""
        size = calculate_position_size(
            self.portfolio,
            Decimal('150.00'),  # price
            sizing_type='fixed',
            size_value=Decimal('1000.00')
        )

        # $1000 / $150 = 6.66 shares, rounded down to 6
        self.assertEqual(size, 6)

    def test_calculate_position_size_percentage(self):
        """Test percentage position size calculation."""
        size = calculate_position_size(
            self.portfolio,
            Decimal('100.00'),  # price
            sizing_type='percentage',
            size_value=Decimal('10.00')  # 10% of portfolio
        )

        # 10% of $10,000 = $1,000, at $100/share = 10 shares
        self.assertEqual(size, 10)

    def test_calculate_position_size_shares(self):
        """Test shares position size calculation."""
        size = calculate_position_size(
            self.portfolio,
            Decimal('150.00'),  # price (not used for shares)
            sizing_type='shares',
            size_value=Decimal('50.00')
        )

        self.assertEqual(size, 50)

    def test_check_buying_power_sufficient(self):
        """Test checking buying power with sufficient funds."""
        result = check_buying_power(
            self.portfolio,
            Decimal('5000.00')  # $5000 < $10000 cash
        )

        self.assertTrue(result['has_buying_power'])
        self.assertEqual(result['available_cash'], Decimal('10000.00'))

    def test_check_buying_power_insufficient(self):
        """Test checking buying power with insufficient funds."""
        result = check_buying_power(
            self.portfolio,
            Decimal('15000.00')  # $15000 > $10000 cash
        )

        self.assertFalse(result['has_buying_power'])
        self.assertIn('Insufficient buying power', result['message'])

    def test_requires_approval_above_threshold(self):
        """Test order requires approval when above threshold."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00')  # $1500 > $500 threshold
        )

        result = requires_approval(order, self.user)
        self.assertTrue(result)

    def test_requires_approval_below_threshold(self):
        """Test order doesn't require approval when below threshold."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=2,
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00')  # $300 < $500 threshold
        )

        result = requires_approval(order, self.user)
        self.assertFalse(result)

    def test_validate_order_success(self):
        """Test successful order validation."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00')
        )

        result = validate_order(order)

        self.assertTrue(result['valid'])

    def test_validate_order_invalid_quantity(self):
        """Test order validation fails for invalid quantity."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=0,
            side='buy',
            order_type='market'
        )

        result = validate_order(order)

        self.assertFalse(result['valid'])
        self.assertIn('Quantity must be positive', result['error'])

    def test_validate_order_insufficient_funds(self):
        """Test order validation fails for insufficient funds."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=1000,  # Way too many
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00')  # $150,000 > $10,000 cash
        )

        result = validate_order(order)

        self.assertFalse(result['valid'])
        self.assertIn('Insufficient buying power', result['error'])

    def test_create_trade_from_order(self):
        """Test creating trade from order."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market'
        )

        fill_data = {
            'filled_qty': 10,
            'filled_avg_price': '150.50',
            'commission': '0.00'
        }

        trade = create_trade_from_order(order, fill_data)

        self.assertIsNotNone(trade)
        self.assertEqual(trade.order, order)
        self.assertEqual(trade.symbol, 'AAPL')
        self.assertEqual(trade.quantity, 10)
        self.assertEqual(trade.price, Decimal('150.50'))


class OrderExecutorTests(TestCase):
    """Test cases for OrderExecutor."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            approval_threshold=Decimal('500.00')
        )

        self.broker_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        self.order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00')
        )

        self.executor = OrderExecutor()

    @patch('apps.orders.execution.get_broker_client')
    def test_execute_order_validation_fails(self, mock_get_client):
        """Test order execution fails validation."""
        # Invalid order (0 quantity)
        bad_order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=0,
            side='buy',
            order_type='market'
        )

        result = asyncio.run(self.executor.execute_order(bad_order.id))

        self.assertFalse(result['success'])
        bad_order.refresh_from_db()
        self.assertEqual(bad_order.status, 'rejected')

    @patch('apps.orders.execution.get_broker_client')
    def test_execute_order_requires_approval(self, mock_get_client):
        """Test order execution triggers approval workflow."""
        # Large order requiring approval
        large_order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=50,
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00')  # $7500 > $500 threshold
        )

        result = asyncio.run(self.executor.execute_order(large_order.id))

        self.assertTrue(result['requires_approval'])
        large_order.refresh_from_db()
        self.assertEqual(large_order.status, 'pending_approval')
        self.assertTrue(large_order.approval_required)


class OrderAPITests(APITestCase):
    """Test cases for Order API endpoints."""

    def setUp(self):
        """Set up test client and data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.broker_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    def test_list_orders(self):
        """Test listing user's orders."""
        Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market'
        )

        response = self.client.get('/api/orders/orders/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_order_via_api(self):
        """Test creating order via API."""
        data = {
            'portfolio': str(self.portfolio.id),
            'symbol': 'AAPL',
            'quantity': 10,
            'side': 'buy',
            'order_type': 'market'
        }

        response = self.client.post(
            '/api/orders/orders/',
            data,
            format='json'
        )

        self.assertIn(response.status_code, [200, 201])

    def test_list_orders_unauthenticated(self):
        """Test listing orders requires authentication."""
        self.client.credentials()

        response = self.client.get('/api/orders/orders/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_approve_order(self):
        """Test approving an order."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=50,
            side='buy',
            order_type='market',
            status='pending_approval',
            approval_required=True
        )

        response = self.client.post(
            f'/api/orders/orders/{order.id}/approve/',
            format='json'
        )

        self.assertIn(response.status_code, [200, 202])

    def test_reject_order(self):
        """Test rejecting an order."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=50,
            side='buy',
            order_type='market',
            status='pending_approval',
            approval_required=True
        )

        response = self.client.post(
            f'/api/orders/orders/{order.id}/reject/',
            {'reason': 'Not interested'},
            format='json'
        )

        self.assertIn(response.status_code, [200, 202])

    def test_cancel_order(self):
        """Test canceling an order."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            order_type='market',
            status='pending'
        )

        response = self.client.post(
            f'/api/orders/orders/{order.id}/cancel/',
            format='json'
        )

        self.assertIn(response.status_code, [200, 202])


class OrderWorkflowTests(TestCase):
    """Integration tests for complete order workflows."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            approval_threshold=Decimal('500.00')
        )

        self.broker_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

    def test_hitl_approval_workflow(self):
        """Test human-in-the-loop approval workflow."""
        # 1. Create large order
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=50,
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00'),  # $7500 > threshold
            approval_required=True,
            status='pending_approval'
        )

        # 2. Verify requires approval
        self.assertTrue(order.approval_required)
        self.assertEqual(order.status, 'pending_approval')

        # 3. Approve order
        order.status = 'approved'
        order.approved_at = timezone.now()
        order.save()

        # 4. Verify approved
        self.assertEqual(order.status, 'approved')
        self.assertIsNotNone(order.approved_at)
