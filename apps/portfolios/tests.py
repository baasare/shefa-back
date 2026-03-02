"""
Comprehensive test suite for the portfolios app.
Tests portfolio management, P&L tracking, analytics, and API endpoints.
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

from apps.portfolios.models import Portfolio, Position, PortfolioSnapshot
from apps.portfolios.services import (
    calculate_portfolio_equity,
    calculate_position_pnl,
    reconcile_portfolio,
    update_position_from_trade,
    close_position
)
from apps.portfolios.analytics import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_sortino_ratio,
    calculate_cagr
)
from apps.orders.models import Trade
from apps.brokers.models import BrokerConnection
from apps.brokers.encryption import encrypt_api_key

User = get_user_model()


class PortfolioModelTests(TestCase):
    """Test cases for Portfolio model."""

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

    def test_create_portfolio(self):
        """Test creating a portfolio."""
        portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        self.assertEqual(portfolio.user, self.user)
        self.assertEqual(portfolio.name, 'Test Portfolio')
        self.assertEqual(portfolio.type, 'paper')
        self.assertEqual(portfolio.cash, Decimal('10000.00'))
        self.assertTrue(portfolio.is_active)

    def test_portfolio_string_representation(self):
        """Test __str__ method."""
        portfolio = Portfolio.objects.create(
            user=self.user,
            name='My Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        expected = f"{self.user.email} - My Portfolio"
        self.assertEqual(str(portfolio), expected)

    def test_portfolio_equity_calculation(self):
        """Test portfolio equity calculation."""
        portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('5000.00'),
            broker_connection=self.broker_connection
        )

        # Add position
        Position.objects.create(
            portfolio=portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        equity = calculate_portfolio_equity(portfolio)

        # Cash: $5000 + Position value: 10 * $160 = $6600
        self.assertEqual(equity, Decimal('6600.00'))

    def test_portfolio_types(self):
        """Test paper vs live portfolio types."""
        paper_portfolio = Portfolio.objects.create(
            user=self.user,
            name='Paper Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        live_portfolio = Portfolio.objects.create(
            user=self.user,
            name='Live Portfolio',
            type='live',
            cash=Decimal('5000.00'),
            broker_connection=self.broker_connection
        )

        self.assertEqual(paper_portfolio.type, 'paper')
        self.assertEqual(live_portfolio.type, 'live')

    def test_portfolio_cascade_delete(self):
        """Test portfolio is deleted when user is deleted."""
        portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )
        portfolio_id = portfolio.id

        self.user.delete()

        with self.assertRaises(Portfolio.DoesNotExist):
            Portfolio.objects.get(id=portfolio_id)


class PositionModelTests(TestCase):
    """Test cases for Position model."""

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

    def test_create_position(self):
        """Test creating a position."""
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('155.00')
        )

        self.assertEqual(position.portfolio, self.portfolio)
        self.assertEqual(position.symbol, 'AAPL')
        self.assertEqual(position.quantity, 10)
        self.assertEqual(position.avg_entry_price, Decimal('150.00'))

    def test_position_unrealized_pnl(self):
        """Test unrealized P&L calculation."""
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        # Unrealized P&L: (160 - 150) * 10 = $100
        self.assertEqual(position.unrealized_pnl, Decimal('100.00'))

    def test_position_unrealized_pnl_percentage(self):
        """Test unrealized P&L percentage."""
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('165.00')
        )

        # P&L %: (165 - 150) / 150 * 100 = 10%
        self.assertEqual(position.unrealized_pnl_pct, Decimal('10.00'))

    def test_position_market_value(self):
        """Test position market value calculation."""
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        # Market value: 10 * $160 = $1600
        self.assertEqual(position.market_value, Decimal('1600.00'))

    def test_position_cost_basis(self):
        """Test position cost basis calculation."""
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        # Cost basis: 10 * $150 = $1500
        self.assertEqual(position.cost_basis, Decimal('1500.00'))

    def test_position_string_representation(self):
        """Test __str__ method."""
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        expected = f"10 AAPL @ $150.00"
        self.assertEqual(str(position), expected)


class PortfolioSnapshotTests(TestCase):
    """Test cases for PortfolioSnapshot model."""

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

    def test_create_snapshot(self):
        """Test creating a portfolio snapshot."""
        snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.portfolio,
            date=timezone.now().date(),
            equity=Decimal('10500.00'),
            cash=Decimal('5000.00'),
            positions_value=Decimal('5500.00')
        )

        self.assertEqual(snapshot.portfolio, self.portfolio)
        self.assertEqual(snapshot.equity, Decimal('10500.00'))
        self.assertEqual(snapshot.cash, Decimal('5000.00'))

    def test_snapshot_daily_pnl(self):
        """Test daily P&L calculation."""
        # Yesterday's snapshot
        yesterday = timezone.now().date() - timedelta(days=1)
        PortfolioSnapshot.objects.create(
            portfolio=self.portfolio,
            date=yesterday,
            equity=Decimal('10000.00')
        )

        # Today's snapshot
        today_snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.portfolio,
            date=timezone.now().date(),
            equity=Decimal('10500.00')
        )

        # Daily P&L: $10500 - $10000 = $500
        self.assertEqual(today_snapshot.daily_pnl, Decimal('500.00'))

    def test_snapshot_string_representation(self):
        """Test __str__ method."""
        date = timezone.now().date()
        snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.portfolio,
            date=date,
            equity=Decimal('10500.00')
        )

        expected = f"{self.portfolio.name} - {date}"
        self.assertEqual(str(snapshot), expected)


class PortfolioServicesTests(TestCase):
    """Test cases for portfolio services."""

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

    def test_calculate_portfolio_equity(self):
        """Test portfolio equity calculation."""
        # Add positions
        Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        Position.objects.create(
            portfolio=self.portfolio,
            symbol='MSFT',
            quantity=5,
            avg_entry_price=Decimal('300.00'),
            current_price=Decimal('310.00')
        )

        equity = calculate_portfolio_equity(self.portfolio)

        # Cash: $10000 + AAPL: 10*160 + MSFT: 5*310 = $10000 + $1600 + $1550 = $13150
        self.assertEqual(equity, Decimal('13150.00'))

    def test_calculate_position_pnl_buy(self):
        """Test position P&L calculation for buy."""
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        pnl = calculate_position_pnl(position, Decimal('160.00'))

        # P&L: (160 - 150) * 10 = $100
        self.assertEqual(pnl['unrealized_pnl'], Decimal('100.00'))
        self.assertEqual(pnl['unrealized_pnl_pct'], Decimal('6.67'))

    def test_update_position_from_buy_trade(self):
        """Test updating position from buy trade."""
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00')
        )

        position = update_position_from_trade(trade)

        self.assertEqual(position.symbol, 'AAPL')
        self.assertEqual(position.quantity, 10)
        self.assertEqual(position.avg_entry_price, Decimal('150.00'))

    def test_update_position_from_additional_buy(self):
        """Test updating position from additional buy (averaging)."""
        # Initial position
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00')
        )

        # Buy more at different price
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('160.00')
        )

        updated_position = update_position_from_trade(trade)

        # New avg: (10*150 + 10*160) / 20 = $155
        self.assertEqual(updated_position.quantity, 20)
        self.assertEqual(updated_position.avg_entry_price, Decimal('155.00'))

    def test_update_position_from_sell_trade(self):
        """Test updating position from sell trade."""
        # Initial position
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00')
        )

        # Sell half
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=5,
            side='sell',
            price=Decimal('160.00')
        )

        updated_position = update_position_from_trade(trade)

        self.assertEqual(updated_position.quantity, 5)
        # Avg entry price stays the same for FIFO
        self.assertEqual(updated_position.avg_entry_price, Decimal('150.00'))

    def test_close_position(self):
        """Test closing a position completely."""
        position = Position.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        # Sell all
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='sell',
            price=Decimal('160.00')
        )

        result = close_position(position, trade)

        self.assertTrue(result['closed'])
        # Position should be deleted
        with self.assertRaises(Position.DoesNotExist):
            Position.objects.get(id=position.id)

    @patch('apps.portfolios.services.get_broker_client')
    def test_reconcile_portfolio(self, mock_get_client):
        """Test portfolio reconciliation with broker."""
        # Mock broker data
        mock_client = Mock()
        mock_client.get_account_info = AsyncMock(return_value={
            'cash': '9000.00',
            'portfolio_value': '11000.00'
        })
        mock_client.get_positions = AsyncMock(return_value=[
            {
                'symbol': 'AAPL',
                'qty': 10,
                'avg_entry_price': '150.00',
                'current_price': '160.00'
            }
        ])
        mock_get_client.return_value = mock_client

        result = asyncio.run(reconcile_portfolio(self.portfolio))

        self.assertTrue(result['success'])
        self.portfolio.refresh_from_db()
        self.assertEqual(self.portfolio.cash, Decimal('9000.00'))


class PortfolioAnalyticsTests(TestCase):
    """Test cases for portfolio analytics."""

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

    def test_calculate_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        # Create snapshots with positive returns
        base_date = timezone.now().date()

        for i in range(30):
            date = base_date - timedelta(days=i)
            equity = Decimal('10000.00') + Decimal(str(i * 50))
            PortfolioSnapshot.objects.create(
                portfolio=self.portfolio,
                date=date,
                equity=equity
            )

        sharpe = calculate_sharpe_ratio(self.portfolio)

        self.assertIsNotNone(sharpe)
        self.assertGreater(sharpe, 0)

    def test_calculate_max_drawdown(self):
        """Test max drawdown calculation."""
        base_date = timezone.now().date()

        # Create equity curve with a drawdown
        equities = [10000, 10500, 10800, 9500, 9000, 9500, 10000, 10500]

        for i, equity in enumerate(equities):
            date = base_date - timedelta(days=len(equities) - i - 1)
            PortfolioSnapshot.objects.create(
                portfolio=self.portfolio,
                date=date,
                equity=Decimal(str(equity))
            )

        max_dd = calculate_max_drawdown(self.portfolio)

        self.assertIsNotNone(max_dd)
        # Max drawdown from 10800 to 9000 = -16.67%
        self.assertLess(max_dd, 0)

    def test_calculate_cagr(self):
        """Test CAGR calculation."""
        base_date = timezone.now().date()
        start_date = base_date - timedelta(days=365)

        # Starting equity
        PortfolioSnapshot.objects.create(
            portfolio=self.portfolio,
            date=start_date,
            equity=Decimal('10000.00')
        )

        # Ending equity (20% gain)
        PortfolioSnapshot.objects.create(
            portfolio=self.portfolio,
            date=base_date,
            equity=Decimal('12000.00')
        )

        cagr = calculate_cagr(self.portfolio)

        self.assertIsNotNone(cagr)
        # CAGR should be approximately 20%
        self.assertGreater(cagr, Decimal('19'))
        self.assertLess(cagr, Decimal('21'))

    def test_calculate_sortino_ratio(self):
        """Test Sortino ratio calculation."""
        base_date = timezone.now().date()

        # Create snapshots with mixed returns
        equities = [10000, 10200, 10100, 10300, 10250, 10400, 10350, 10500]

        for i, equity in enumerate(equities):
            date = base_date - timedelta(days=len(equities) - i - 1)
            PortfolioSnapshot.objects.create(
                portfolio=self.portfolio,
                date=date,
                equity=Decimal(str(equity))
            )

        sortino = calculate_sortino_ratio(self.portfolio)

        self.assertIsNotNone(sortino)


class PortfolioAPITests(APITestCase):
    """Test cases for Portfolio API endpoints."""

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

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    def test_list_portfolios(self):
        """Test listing user's portfolios."""
        Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        response = self.client.get('/api/portfolios/portfolios/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_portfolio(self):
        """Test creating portfolio via API."""
        data = {
            'name': 'New Portfolio',
            'type': 'paper',
            'cash': '10000.00',
            'broker_connection': str(self.broker_connection.id)
        }

        response = self.client.post(
            '/api/portfolios/portfolios/',
            data,
            format='json'
        )

        self.assertIn(response.status_code, [200, 201])

    def test_list_portfolios_unauthenticated(self):
        """Test listing portfolios requires authentication."""
        self.client.credentials()

        response = self.client.get('/api/portfolios/portfolios/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_portfolio_performance(self):
        """Test getting portfolio performance metrics."""
        portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        response = self.client.get(
            f'/api/portfolios/portfolios/{portfolio.id}/performance/'
        )

        self.assertIn(response.status_code, [200, 404])

    def test_list_positions(self):
        """Test listing portfolio positions."""
        portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

        Position.objects.create(
            portfolio=portfolio,
            symbol='AAPL',
            quantity=10,
            avg_entry_price=Decimal('150.00'),
            current_price=Decimal('160.00')
        )

        response = self.client.get('/api/portfolios/positions/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PortfolioIntegrationTests(TestCase):
    """Integration tests for portfolio workflows."""

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

    def test_complete_trading_workflow(self):
        """Test complete buy-sell workflow with P&L tracking."""
        # 1. Buy trade
        buy_trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00')
        )

        position = update_position_from_trade(buy_trade)

        # Verify position created
        self.assertEqual(position.quantity, 10)
        self.assertEqual(position.avg_entry_price, Decimal('150.00'))

        # 2. Update current price
        position.current_price = Decimal('160.00')
        position.save()

        # Verify unrealized P&L
        self.assertEqual(position.unrealized_pnl, Decimal('100.00'))

        # 3. Sell trade
        sell_trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='sell',
            price=Decimal('160.00')
        )

        result = close_position(position, sell_trade)

        # Verify position closed
        self.assertTrue(result['closed'])
        self.assertEqual(result['realized_pnl'], Decimal('100.00'))
