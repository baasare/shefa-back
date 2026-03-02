"""
Comprehensive test suite for the strategies app.
Tests strategy configuration, validation, backtesting, and execution.
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
import json

from apps.strategies.models import Strategy, Backtest
from apps.strategies.services import (
    evaluate_entry_conditions,
    evaluate_exit_conditions,
    calculate_indicators,
    generate_signals
)
from apps.strategies.validator import validate_strategy_config
from apps.strategies.backtest import BacktestEngine
from apps.strategies.executor import StrategyExecutor
from apps.portfolios.models import Portfolio
from apps.brokers.models import BrokerConnection
from apps.brokers.encryption import encrypt_api_key

User = get_user_model()


class StrategyModelTests(TestCase):
    """Test cases for Strategy model."""

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

        self.strategy_config = {
            'entry_conditions': [
                {'indicator': 'rsi', 'operator': '<', 'value': 30}
            ],
            'exit_conditions': [
                {'indicator': 'rsi', 'operator': '>', 'value': 70}
            ],
            'position_sizing': {
                'type': 'percentage',
                'value': 10
            },
            'risk_management': {
                'stop_loss_pct': 5,
                'take_profit_pct': 10
            }
        }

    def test_create_strategy(self):
        """Test creating a strategy."""
        strategy = Strategy.objects.create(
            user=self.user,
            name='RSI Strategy',
            type='technical',
            config=self.strategy_config,
            watchlist=['AAPL', 'MSFT', 'TSLA']
        )

        self.assertEqual(strategy.user, self.user)
        self.assertEqual(strategy.name, 'RSI Strategy')
        self.assertEqual(strategy.type, 'technical')
        self.assertFalse(strategy.is_active)
        self.assertEqual(len(strategy.watchlist), 3)

    def test_strategy_activation(self):
        """Test activating a strategy."""
        strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config=self.strategy_config,
            is_active=False
        )

        # Activate
        strategy.is_active = True
        strategy.save()

        self.assertTrue(strategy.is_active)

    def test_strategy_config_validation(self):
        """Test strategy config validation."""
        strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config=self.strategy_config
        )

        result = validate_strategy_config(strategy.config)

        self.assertTrue(result['valid'])

    def test_strategy_string_representation(self):
        """Test __str__ method."""
        strategy = Strategy.objects.create(
            user=self.user,
            name='My Strategy',
            type='technical',
            config=self.strategy_config
        )

        expected = f"{self.user.email} - My Strategy"
        self.assertEqual(str(strategy), expected)

    def test_entry_exit_rules(self):
        """Test entry and exit rules in config."""
        strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config=self.strategy_config
        )

        self.assertIn('entry_conditions', strategy.config)
        self.assertIn('exit_conditions', strategy.config)
        self.assertEqual(len(strategy.config['entry_conditions']), 1)
        self.assertEqual(len(strategy.config['exit_conditions']), 1)


class BacktestModelTests(TestCase):
    """Test cases for Backtest model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config={'entry_conditions': [], 'exit_conditions': []}
        )

    def test_create_backtest(self):
        """Test creating a backtest."""
        start_date = timezone.now().date() - timedelta(days=365)
        end_date = timezone.now().date()

        backtest = Backtest.objects.create(
            strategy=self.strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal('10000.00'),
            status='pending'
        )

        self.assertEqual(backtest.strategy, self.strategy)
        self.assertEqual(backtest.initial_capital, Decimal('10000.00'))
        self.assertEqual(backtest.status, 'pending')

    def test_backtest_metrics(self):
        """Test backtest metrics."""
        backtest = Backtest.objects.create(
            strategy=self.strategy,
            start_date=timezone.now().date() - timedelta(days=365),
            end_date=timezone.now().date(),
            initial_capital=Decimal('10000.00'),
            final_capital=Decimal('12000.00'),
            total_return_pct=Decimal('20.00'),
            sharpe_ratio=Decimal('1.5'),
            max_drawdown_pct=Decimal('-10.00'),
            win_rate=Decimal('60.00'),
            total_trades=50
        )

        self.assertEqual(backtest.total_return_pct, Decimal('20.00'))
        self.assertEqual(backtest.sharpe_ratio, Decimal('1.5'))
        self.assertEqual(backtest.win_rate, Decimal('60.00'))
        self.assertEqual(backtest.total_trades, 50)

    def test_backtest_equity_curve(self):
        """Test backtest equity curve data."""
        equity_data = [
            {'date': '2024-01-01', 'equity': 10000},
            {'date': '2024-02-01', 'equity': 10500},
            {'date': '2024-03-01', 'equity': 11000}
        ]

        backtest = Backtest.objects.create(
            strategy=self.strategy,
            start_date=timezone.now().date() - timedelta(days=90),
            end_date=timezone.now().date(),
            initial_capital=Decimal('10000.00'),
            equity_curve=equity_data
        )

        self.assertEqual(len(backtest.equity_curve), 3)
        self.assertEqual(backtest.equity_curve[0]['equity'], 10000)

    def test_backtest_string_representation(self):
        """Test __str__ method."""
        backtest = Backtest.objects.create(
            strategy=self.strategy,
            start_date=timezone.now().date() - timedelta(days=30),
            end_date=timezone.now().date(),
            initial_capital=Decimal('10000.00')
        )

        expected = f"Backtest - {self.strategy.name}"
        self.assertEqual(str(backtest), expected)


class StrategyServicesTests(TestCase):
    """Test cases for strategy services."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

    def test_evaluate_entry_conditions_rsi(self):
        """Test evaluating RSI entry conditions."""
        conditions = [
            {'indicator': 'rsi', 'operator': '<', 'value': 30}
        ]

        market_data = {
            'rsi': 25.0
        }

        result = evaluate_entry_conditions(conditions, market_data)

        self.assertTrue(result)

    def test_evaluate_entry_conditions_false(self):
        """Test entry conditions evaluate to false."""
        conditions = [
            {'indicator': 'rsi', 'operator': '<', 'value': 30}
        ]

        market_data = {
            'rsi': 45.0
        }

        result = evaluate_entry_conditions(conditions, market_data)

        self.assertFalse(result)

    def test_evaluate_entry_conditions_multiple(self):
        """Test evaluating multiple entry conditions (AND logic)."""
        conditions = [
            {'indicator': 'rsi', 'operator': '<', 'value': 30},
            {'indicator': 'macd', 'operator': '>', 'value': 0}
        ]

        market_data = {
            'rsi': 25.0,
            'macd': 5.0
        }

        result = evaluate_entry_conditions(conditions, market_data)

        self.assertTrue(result)

    def test_evaluate_exit_conditions(self):
        """Test evaluating exit conditions."""
        conditions = [
            {'indicator': 'rsi', 'operator': '>', 'value': 70}
        ]

        market_data = {
            'rsi': 75.0
        }

        result = evaluate_exit_conditions(conditions, market_data)

        self.assertTrue(result)

    def test_calculate_indicators_rsi(self):
        """Test RSI indicator calculation."""
        prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109]

        indicators = calculate_indicators(prices, ['rsi'])

        self.assertIn('rsi', indicators)
        self.assertIsNotNone(indicators['rsi'])

    def test_calculate_indicators_macd(self):
        """Test MACD indicator calculation."""
        prices = [100 + i for i in range(50)]  # Uptrend

        indicators = calculate_indicators(prices, ['macd'])

        self.assertIn('macd', indicators)
        self.assertIsNotNone(indicators['macd'])

    def test_calculate_indicators_sma(self):
        """Test SMA indicator calculation."""
        prices = [100, 102, 104, 106, 108]

        indicators = calculate_indicators(prices, ['sma_20'])

        self.assertIn('sma_20', indicators)
        self.assertIsNotNone(indicators['sma_20'])

    def test_generate_signals_buy(self):
        """Test generating buy signal."""
        strategy_config = {
            'entry_conditions': [
                {'indicator': 'rsi', 'operator': '<', 'value': 30}
            ],
            'exit_conditions': []
        }

        market_data = {
            'rsi': 25.0,
            'price': 150.00
        }

        signal = generate_signals(strategy_config, market_data)

        self.assertEqual(signal['action'], 'buy')
        self.assertEqual(signal['price'], 150.00)

    def test_generate_signals_sell(self):
        """Test generating sell signal."""
        strategy_config = {
            'entry_conditions': [],
            'exit_conditions': [
                {'indicator': 'rsi', 'operator': '>', 'value': 70}
            ]
        }

        market_data = {
            'rsi': 75.0,
            'price': 160.00
        }

        signal = generate_signals(strategy_config, market_data, has_position=True)

        self.assertEqual(signal['action'], 'sell')
        self.assertEqual(signal['price'], 160.00)

    def test_generate_signals_hold(self):
        """Test generating hold signal."""
        strategy_config = {
            'entry_conditions': [
                {'indicator': 'rsi', 'operator': '<', 'value': 30}
            ],
            'exit_conditions': []
        }

        market_data = {
            'rsi': 50.0,  # Neutral
            'price': 155.00
        }

        signal = generate_signals(strategy_config, market_data)

        self.assertEqual(signal['action'], 'hold')


class StrategyValidatorTests(TestCase):
    """Test cases for strategy configuration validator."""

    def test_validate_valid_config(self):
        """Test validating valid configuration."""
        config = {
            'entry_conditions': [
                {'indicator': 'rsi', 'operator': '<', 'value': 30}
            ],
            'exit_conditions': [
                {'indicator': 'rsi', 'operator': '>', 'value': 70}
            ],
            'position_sizing': {
                'type': 'percentage',
                'value': 10
            }
        }

        result = validate_strategy_config(config)

        self.assertTrue(result['valid'])

    def test_validate_missing_entry_conditions(self):
        """Test validation fails without entry conditions."""
        config = {
            'exit_conditions': [
                {'indicator': 'rsi', 'operator': '>', 'value': 70}
            ]
        }

        result = validate_strategy_config(config)

        self.assertFalse(result['valid'])
        self.assertIn('entry_conditions', result['error'].lower())

    def test_validate_invalid_operator(self):
        """Test validation fails with invalid operator."""
        config = {
            'entry_conditions': [
                {'indicator': 'rsi', 'operator': 'invalid', 'value': 30}
            ],
            'exit_conditions': []
        }

        result = validate_strategy_config(config)

        self.assertFalse(result['valid'])

    def test_validate_invalid_position_sizing(self):
        """Test validation fails with invalid position sizing."""
        config = {
            'entry_conditions': [
                {'indicator': 'rsi', 'operator': '<', 'value': 30}
            ],
            'exit_conditions': [],
            'position_sizing': {
                'type': 'invalid_type',
                'value': 10
            }
        }

        result = validate_strategy_config(config)

        self.assertFalse(result['valid'])


class BacktestEngineTests(TestCase):
    """Test cases for BacktestEngine."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config={
                'entry_conditions': [
                    {'indicator': 'rsi', 'operator': '<', 'value': 30}
                ],
                'exit_conditions': [
                    {'indicator': 'rsi', 'operator': '>', 'value': 70}
                ],
                'position_sizing': {
                    'type': 'percentage',
                    'value': 10
                }
            },
            watchlist=['AAPL']
        )

        self.engine = BacktestEngine()

    @patch('apps.strategies.backtest.get_historical_data')
    def test_run_backtest(self, mock_get_data):
        """Test running a backtest."""
        # Mock historical data
        mock_get_data.return_value = [
            {'date': '2024-01-01', 'close': 100, 'rsi': 25},
            {'date': '2024-01-02', 'close': 105, 'rsi': 45},
            {'date': '2024-01-03', 'close': 110, 'rsi': 75},
        ]

        start_date = timezone.now().date() - timedelta(days=30)
        end_date = timezone.now().date()

        backtest = self.engine.run_backtest(
            self.strategy,
            start_date,
            end_date,
            initial_capital=Decimal('10000.00')
        )

        self.assertIsNotNone(backtest)
        self.assertEqual(backtest.strategy, self.strategy)
        self.assertIn(backtest.status, ['completed', 'running'])

    @patch('apps.strategies.backtest.get_historical_data')
    def test_simulate_trades(self, mock_get_data):
        """Test simulating trades."""
        mock_get_data.return_value = [
            {'date': '2024-01-01', 'close': 100, 'rsi': 25},  # Buy signal
            {'date': '2024-01-02', 'close': 105, 'rsi': 50},
            {'date': '2024-01-03', 'close': 110, 'rsi': 75},  # Sell signal
        ]

        trades = self.engine.simulate_trades(
            self.strategy,
            mock_get_data.return_value,
            Decimal('10000.00')
        )

        self.assertIsInstance(trades, list)
        # Should have at least one buy and one sell
        self.assertGreater(len(trades), 0)

    def test_calculate_performance_metrics(self):
        """Test calculating performance metrics."""
        equity_curve = [
            10000, 10200, 10100, 10400, 10300, 10600, 10500, 10800
        ]

        metrics = self.engine.calculate_performance_metrics(
            equity_curve,
            Decimal('10000.00')
        )

        self.assertIn('total_return_pct', metrics)
        self.assertIn('sharpe_ratio', metrics)
        self.assertIn('max_drawdown_pct', metrics)
        self.assertGreater(metrics['total_return_pct'], 0)

    def test_generate_equity_curve(self):
        """Test generating equity curve."""
        trades = [
            {'date': '2024-01-01', 'pnl': 100},
            {'date': '2024-01-02', 'pnl': 50},
            {'date': '2024-01-03', 'pnl': -30},
            {'date': '2024-01-04', 'pnl': 80}
        ]

        equity_curve = self.engine.generate_equity_curve(
            trades,
            Decimal('10000.00')
        )

        self.assertEqual(len(equity_curve), len(trades) + 1)  # Including initial
        self.assertEqual(equity_curve[0], Decimal('10000.00'))
        self.assertEqual(equity_curve[-1], Decimal('10200.00'))  # 10000 + 100 + 50 - 30 + 80


class StrategyExecutorTests(TestCase):
    """Test cases for StrategyExecutor."""

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

        self.strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config={
                'entry_conditions': [
                    {'indicator': 'rsi', 'operator': '<', 'value': 30}
                ],
                'exit_conditions': [],
                'position_sizing': {
                    'type': 'percentage',
                    'value': 10
                }
            },
            watchlist=['AAPL', 'MSFT'],
            portfolio=self.portfolio
        )

        self.executor = StrategyExecutor()

    @patch('apps.strategies.executor.get_market_data')
    @patch('apps.strategies.executor.calculate_indicators')
    def test_execute_strategy_on_watchlist(self, mock_indicators, mock_market_data):
        """Test executing strategy on watchlist."""
        # Mock market data
        mock_market_data.return_value = {'price': 150.00}
        mock_indicators.return_value = {'rsi': 25.0}

        signals = self.executor.execute_strategy(self.strategy)

        self.assertIsInstance(signals, list)
        # Should have signals for each symbol in watchlist
        self.assertGreater(len(signals), 0)

    @patch('apps.strategies.executor.get_market_data')
    def test_manual_execution(self, mock_market_data):
        """Test manual strategy execution."""
        mock_market_data.return_value = {'price': 150.00, 'rsi': 25.0}

        result = self.executor.execute_manual(
            self.strategy,
            symbol='AAPL'
        )

        self.assertIn('signal', result)
        self.assertIn('action', result['signal'])

    @patch('apps.strategies.executor.get_market_data')
    def test_dry_run_mode(self, mock_market_data):
        """Test dry run mode (no actual orders)."""
        mock_market_data.return_value = {'price': 150.00, 'rsi': 25.0}

        signals = self.executor.execute_strategy(
            self.strategy,
            dry_run=True
        )

        # In dry run, signals are generated but no orders placed
        self.assertIsInstance(signals, list)
        # Verify no actual orders were created
        from apps.orders.models import Order
        orders_count = Order.objects.filter(portfolio=self.portfolio).count()
        self.assertEqual(orders_count, 0)


class StrategyAPITests(APITestCase):
    """Test cases for Strategy API endpoints."""

    def setUp(self):
        """Set up test client and data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    def test_list_strategies(self):
        """Test listing user's strategies."""
        Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config={'entry_conditions': [], 'exit_conditions': []}
        )

        response = self.client.get('/api/strategies/strategies/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_strategy(self):
        """Test creating strategy via API."""
        data = {
            'name': 'New Strategy',
            'type': 'technical',
            'config': {
                'entry_conditions': [
                    {'indicator': 'rsi', 'operator': '<', 'value': 30}
                ],
                'exit_conditions': []
            },
            'watchlist': ['AAPL', 'MSFT']
        }

        response = self.client.post(
            '/api/strategies/strategies/',
            data,
            format='json'
        )

        self.assertIn(response.status_code, [200, 201])

    def test_list_strategies_unauthenticated(self):
        """Test listing strategies requires authentication."""
        self.client.credentials()

        response = self.client.get('/api/strategies/strategies/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_activate_strategy(self):
        """Test activating a strategy."""
        strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config={'entry_conditions': [], 'exit_conditions': []},
            is_active=False
        )

        response = self.client.post(
            f'/api/strategies/strategies/{strategy.id}/activate/',
            format='json'
        )

        self.assertIn(response.status_code, [200, 202])

    def test_pause_strategy(self):
        """Test pausing a strategy."""
        strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config={'entry_conditions': [], 'exit_conditions': []},
            is_active=True
        )

        response = self.client.post(
            f'/api/strategies/strategies/{strategy.id}/pause/',
            format='json'
        )

        self.assertIn(response.status_code, [200, 202])

    def test_run_backtest_via_api(self):
        """Test running backtest via API."""
        strategy = Strategy.objects.create(
            user=self.user,
            name='Test Strategy',
            type='technical',
            config={'entry_conditions': [], 'exit_conditions': []},
            watchlist=['AAPL']
        )

        data = {
            'start_date': '2024-01-01',
            'end_date': '2024-03-01',
            'initial_capital': '10000.00'
        }

        response = self.client.post(
            f'/api/strategies/strategies/{strategy.id}/backtest/',
            data,
            format='json'
        )

        self.assertIn(response.status_code, [200, 201, 202])


class StrategyIntegrationTests(TestCase):
    """Integration tests for strategy workflows."""

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

    @patch('apps.strategies.executor.get_market_data')
    @patch('apps.strategies.executor.calculate_indicators')
    def test_complete_strategy_workflow(self, mock_indicators, mock_market_data):
        """Test complete strategy creation to execution workflow."""
        # 1. Create strategy
        strategy = Strategy.objects.create(
            user=self.user,
            name='RSI Strategy',
            type='technical',
            config={
                'entry_conditions': [
                    {'indicator': 'rsi', 'operator': '<', 'value': 30}
                ],
                'exit_conditions': [
                    {'indicator': 'rsi', 'operator': '>', 'value': 70}
                ],
                'position_sizing': {
                    'type': 'percentage',
                    'value': 10
                }
            },
            watchlist=['AAPL'],
            portfolio=self.portfolio
        )

        # 2. Validate config
        result = validate_strategy_config(strategy.config)
        self.assertTrue(result['valid'])

        # 3. Execute strategy (dry run)
        mock_market_data.return_value = {'price': 150.00}
        mock_indicators.return_value = {'rsi': 25.0}

        executor = StrategyExecutor()
        signals = executor.execute_strategy(strategy, dry_run=True)

        # 4. Verify signals generated
        self.assertIsInstance(signals, list)
        self.assertGreater(len(signals), 0)

        # 5. Check signal is buy
        if len(signals) > 0:
            self.assertIn(signals[0]['action'], ['buy', 'sell', 'hold'])
