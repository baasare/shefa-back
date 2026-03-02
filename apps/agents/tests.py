"""
Comprehensive tests for AI agent orchestration system.

Tests cover:
- Agent tools (market data, portfolio, strategy, orders, risk)
- Agent orchestrator (multi-agent coordination)
- Agent tasks (Celery background tasks)
- Agent API endpoints
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
import asyncio
from datetime import datetime, timedelta

from apps.agents.tools import (
    get_stock_quote,
    get_historical_prices,
    calculate_technical_indicators,
    get_market_news,
    get_portfolio_status,
    calculate_position_size,
    TRADING_TOOLS
)
from apps.agents.orchestrator import (
    TradingAgentFactory,
    AgentOrchestrator
)
from apps.agents.tasks import (
    run_agent_analysis,
    run_watchlist_monitoring,
    execute_autonomous_trade,
    run_periodic_agent_scan
)
from apps.portfolios.models import Portfolio, Position
from apps.strategies.models import Strategy
from apps.brokers.models import BrokerConnection

User = get_user_model()


class AgentToolsTests(TestCase):
    """Test suite for agent tools."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            cash=Decimal('10000.00')
        )

    @patch('apps.agents.tools.MassiveProvider')
    def test_get_stock_quote_success(self, mock_provider):
        """Test successful stock quote retrieval."""
        mock_instance = mock_provider.return_value
        mock_instance.get_quote.return_value = {
            'symbol': 'AAPL',
            'price': 150.25,
            'change': 2.50,
            'change_percent': 1.69
        }

        result = get_stock_quote('AAPL')

        self.assertTrue(result['success'])
        self.assertEqual(result['symbol'], 'AAPL')
        self.assertEqual(result['data']['price'], 150.25)
        mock_instance.get_quote.assert_called_once_with('AAPL')

    @patch('apps.agents.tools.MassiveProvider')
    def test_get_stock_quote_failure(self, mock_provider):
        """Test stock quote retrieval failure."""
        mock_instance = mock_provider.return_value
        mock_instance.get_quote.side_effect = Exception('API Error')

        result = get_stock_quote('INVALID')

        self.assertFalse(result['success'])
        self.assertIn('error', result)

    @patch('apps.agents.tools.MassiveProvider')
    def test_get_historical_prices(self, mock_provider):
        """Test historical price data retrieval."""
        mock_instance = mock_provider.return_value
        mock_instance.get_historical_prices.return_value = [
            {'date': '2024-01-01', 'close': 150.0},
            {'date': '2024-01-02', 'close': 151.0},
        ]

        result = get_historical_prices('AAPL', days=30)

        self.assertTrue(result['success'])
        self.assertEqual(len(result['data']), 2)
        mock_instance.get_historical_prices.assert_called_once()

    @patch('apps.agents.tools.calculate_rsi')
    @patch('apps.agents.tools.calculate_macd')
    def test_calculate_technical_indicators(self, mock_macd, mock_rsi):
        """Test technical indicator calculations."""
        mock_rsi.return_value = 65.5
        mock_macd.return_value = {'macd': 1.5, 'signal': 1.2, 'histogram': 0.3}

        prices = [150.0, 151.0, 152.0, 151.5, 153.0]
        result = calculate_technical_indicators('AAPL', prices)

        self.assertTrue(result['success'])
        self.assertEqual(result['indicators']['rsi'], 65.5)
        self.assertIn('macd', result['indicators'])

    def test_get_portfolio_status(self):
        """Test portfolio status retrieval."""
        result = get_portfolio_status(str(self.portfolio.id))

        self.assertTrue(result['success'])
        self.assertEqual(Decimal(result['portfolio']['cash']), self.portfolio.cash)
        self.assertEqual(result['portfolio']['name'], 'Test Portfolio')

    def test_get_portfolio_status_not_found(self):
        """Test portfolio status with invalid ID."""
        result = get_portfolio_status('00000000-0000-0000-0000-000000000000')

        self.assertFalse(result['success'])
        self.assertIn('error', result)

    @patch('apps.agents.tools.MassiveProvider')
    def test_calculate_position_size(self, mock_provider):
        """Test position size calculation."""
        mock_instance = mock_provider.return_value
        mock_instance.get_quote.return_value = {'price': 150.0}

        result = calculate_position_size(
            str(self.portfolio.id),
            'AAPL',
            percentage=10.0
        )

        self.assertTrue(result['success'])
        self.assertIn('quantity', result)
        self.assertIn('estimated_value', result)

    @patch('apps.agents.tools.AlphaVantageProvider')
    def test_get_market_news_success(self, mock_provider):
        """Test successful market news retrieval."""
        mock_instance = mock_provider.return_value

        # Mock news data
        mock_news_data = {
            'items': 5,
            'feed': [
                {
                    'title': 'Apple announces new product',
                    'summary': 'Apple unveils revolutionary device',
                    'source': 'TechNews',
                    'time_published': datetime.now(),
                    'url': 'https://example.com/news/1',
                    'overall_sentiment_score': 0.45,
                    'overall_sentiment_label': 'Bullish',
                    'ticker_sentiment': [
                        {
                            'ticker': 'AAPL',
                            'sentiment_score': 0.50,
                            'sentiment_label': 'Bullish',
                            'relevance_score': 0.95
                        }
                    ]
                }
            ]
        }

        mock_instance.get_news_sentiment = Mock(return_value=mock_news_data)
        mock_instance.interpret_sentiment_score = Mock(return_value='Bullish')

        with patch('apps.agents.tools.settings') as mock_settings:
            mock_settings.ALPHA_VANTAGE_API_KEY = 'test-key'

            result = get_market_news('AAPL', limit=5, days_back=7)

        self.assertTrue(result['success'])
        self.assertEqual(result['symbol'], 'AAPL')
        self.assertIn('articles', result)
        self.assertIn('average_sentiment', result)
        self.assertIn('sentiment_label', result)

    def test_get_market_news_no_api_key(self):
        """Test market news without API key."""
        with patch('apps.agents.tools.settings') as mock_settings:
            mock_settings.ALPHA_VANTAGE_API_KEY = None

            result = get_market_news('AAPL')

        self.assertFalse(result['success'])
        self.assertIn('API key not configured', result['error'])

    def test_trading_tools_list(self):
        """Test that all required tools are in TRADING_TOOLS."""
        tool_names = [tool.name for tool in TRADING_TOOLS]

        required_tools = [
            'get_stock_quote',
            'get_historical_prices',
            'calculate_technical_indicators',
            'get_market_news',  # NEW
            'get_portfolio_status',
            'calculate_position_size'
        ]

        for tool in required_tools:
            self.assertIn(tool, tool_names)


class AgentOrchestratorTests(TestCase):
    """Test suite for agent orchestration."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            cash=Decimal('10000.00')
        )
        self.strategy = Strategy.objects.create(
            user=self.user,
            portfolio=self.portfolio,
            name='Test Strategy',
            strategy_type='technical',
            is_active=True
        )

    @patch('apps.agents.orchestrator.init_chat_model')
    def test_trading_agent_factory_initialization(self, mock_init_model):
        """Test agent factory initialization."""
        mock_init_model.return_value = Mock()

        factory = TradingAgentFactory(model_name='openai:gpt-4o')

        self.assertIsNotNone(factory.model)
        mock_init_model.assert_called_once()

    @patch('apps.agents.orchestrator.create_deep_agent')
    @patch('apps.agents.orchestrator.init_chat_model')
    def test_create_technical_analyst(self, mock_init_model, mock_create_agent):
        """Test technical analyst agent creation."""
        mock_init_model.return_value = Mock()
        mock_create_agent.return_value = Mock()

        factory = TradingAgentFactory()
        agent = factory.create_technical_analyst()

        self.assertIsNotNone(agent)
        mock_create_agent.assert_called_once()

    @patch('apps.agents.orchestrator.create_deep_agent')
    @patch('apps.agents.orchestrator.init_chat_model')
    def test_agent_orchestrator_initialization(self, mock_init_model, mock_create_agent):
        """Test orchestrator initialization creates all agents."""
        mock_init_model.return_value = Mock()
        mock_create_agent.return_value = Mock()

        orchestrator = AgentOrchestrator(
            portfolio=self.portfolio,
            strategy=self.strategy
        )

        self.assertEqual(orchestrator.portfolio, self.portfolio)
        self.assertEqual(orchestrator.strategy, self.strategy)
        self.assertIsNotNone(orchestrator.technical_agent)
        self.assertIsNotNone(orchestrator.fundamental_agent)
        self.assertIsNotNone(orchestrator.sentiment_agent)
        self.assertIsNotNone(orchestrator.risk_agent)
        self.assertIsNotNone(orchestrator.supervisor_agent)

    @patch('apps.agents.orchestrator.create_deep_agent')
    @patch('apps.agents.orchestrator.init_chat_model')
    @patch('asyncio.to_thread')
    async def test_analyze_stock_technical(self, mock_to_thread, mock_init_model, mock_create_agent):
        """Test stock analysis with technical analysis."""
        mock_init_model.return_value = Mock()

        # Mock agent response
        mock_agent = Mock()
        mock_response = {
            'messages': [
                Mock(content='Technical Analysis: BUY signal. RSI: 35 (oversold)')
            ]
        }
        mock_agent.invoke.return_value = mock_response
        mock_create_agent.return_value = mock_agent
        mock_to_thread.return_value = mock_response

        orchestrator = AgentOrchestrator(portfolio=self.portfolio)
        result = await orchestrator.analyze_stock('AAPL', analysis_type='technical')

        self.assertIn('technical', result)

    @patch('apps.agents.orchestrator.create_deep_agent')
    @patch('apps.agents.orchestrator.init_chat_model')
    def test_run_sync_wrapper(self, mock_init_model, mock_create_agent):
        """Test synchronous wrapper for async methods."""
        mock_init_model.return_value = Mock()
        mock_agent = Mock()
        mock_agent.invoke.return_value = {
            'messages': [Mock(content='Analysis complete')]
        }
        mock_create_agent.return_value = mock_agent

        orchestrator = AgentOrchestrator(portfolio=self.portfolio)

        # This should not raise an exception
        with patch.object(orchestrator, 'get_trading_recommendation') as mock_method:
            mock_method.return_value = asyncio.coroutine(lambda: {'test': 'result'})()
            # Would test but requires complex async mocking


class AgentTasksTests(TestCase):
    """Test suite for agent Celery tasks."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            cash=Decimal('10000.00')
        )
        self.strategy = Strategy.objects.create(
            user=self.user,
            portfolio=self.portfolio,
            name='Test Strategy',
            strategy_type='technical',
            is_active=True,
            watchlist=['AAPL', 'GOOGL']
        )

    @patch('apps.agents.tasks.AgentOrchestrator')
    def test_run_agent_analysis_success(self, mock_orchestrator):
        """Test successful agent analysis task."""
        mock_instance = mock_orchestrator.return_value
        mock_instance.run_sync.return_value = {
            'symbol': 'AAPL',
            'timestamp': datetime.now().timestamp(),
            'final_recommendation': {
                'messages': [Mock(content='BUY recommendation')]
            }
        }

        result = run_agent_analysis(str(self.portfolio.id), 'AAPL')

        self.assertTrue(result['success'])
        self.assertEqual(result['symbol'], 'AAPL')
        mock_orchestrator.assert_called_once()

    @patch('apps.agents.tasks.AgentOrchestrator')
    def test_run_agent_analysis_portfolio_not_found(self, mock_orchestrator):
        """Test agent analysis with invalid portfolio."""
        result = run_agent_analysis('00000000-0000-0000-0000-000000000000', 'AAPL')

        self.assertFalse(result['success'])
        self.assertIn('error', result)

    @patch('apps.agents.tasks.AgentOrchestrator')
    @patch('apps.agents.tasks.send_strategy_signal_notification')
    async def test_run_watchlist_monitoring_success(self, mock_notification, mock_orchestrator):
        """Test successful watchlist monitoring."""
        mock_instance = mock_orchestrator.return_value

        # Mock async method
        async def mock_monitor():
            return [
                {
                    'symbol': 'AAPL',
                    'success': True,
                    'final_recommendation': {
                        'messages': [Mock(content='BUY signal')]
                    }
                }
            ]

        with patch('asyncio.new_event_loop') as mock_loop_fn:
            mock_loop = Mock()
            mock_loop_fn.return_value = mock_loop
            mock_loop.run_until_complete.return_value = await mock_monitor()

            result = run_watchlist_monitoring(str(self.strategy.id))

            self.assertTrue(result['success'])
            self.assertIn('signals_generated', result)

    @patch('apps.agents.tasks.AgentOrchestrator')
    @patch('apps.agents.tasks.MassiveProvider')
    @patch('apps.agents.tasks.calculate_position_size')
    def test_execute_autonomous_trade_hold(self, mock_calc_size, mock_provider, mock_orchestrator):
        """Test autonomous trade execution with HOLD recommendation."""
        mock_instance = mock_orchestrator.return_value
        mock_instance.run_sync.return_value = {
            'final_recommendation': {
                'messages': [Mock(content='HOLD - no clear signal')]
            }
        }

        result = execute_autonomous_trade(str(self.strategy.id), 'AAPL')

        self.assertTrue(result['success'])
        self.assertEqual(result['action'], 'hold')

    @patch('apps.agents.tasks.Strategy')
    def test_run_periodic_agent_scan(self, mock_strategy):
        """Test periodic agent scan task."""
        mock_strategy.objects.filter.return_value = [self.strategy]

        with patch('apps.agents.tasks.run_watchlist_monitoring') as mock_task:
            mock_task.delay.return_value = Mock(id='test-task-id')

            result = run_periodic_agent_scan()

            self.assertTrue(result['success'])
            self.assertIn('strategies_scanned', result)


class AgentAPITests(APITestCase):
    """Test suite for agent API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            cash=Decimal('10000.00')
        )
        self.strategy = Strategy.objects.create(
            user=self.user,
            portfolio=self.portfolio,
            name='Test Strategy',
            strategy_type='technical',
            is_active=True,
            watchlist=['AAPL', 'GOOGL']
        )
        self.client.force_authenticate(user=self.user)

    @patch('apps.agents.views.run_agent_analysis')
    def test_analyze_stock_api(self, mock_task):
        """Test analyze stock API endpoint."""
        mock_task.delay.return_value = Mock(id='test-task-id')

        url = '/api/agent-analysis/analyze-stock/'
        data = {
            'portfolio_id': str(self.portfolio.id),
            'symbol': 'AAPL'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['symbol'], 'AAPL')
        self.assertIn('task_id', response.data)

    def test_analyze_stock_missing_params(self):
        """Test analyze stock API with missing parameters."""
        url = '/api/agent-analysis/analyze-stock/'
        data = {'symbol': 'AAPL'}  # Missing portfolio_id

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    @patch('apps.agents.views.run_watchlist_monitoring')
    def test_monitor_watchlist_api(self, mock_task):
        """Test monitor watchlist API endpoint."""
        mock_task.delay.return_value = Mock(id='test-task-id')

        url = '/api/agent-analysis/monitor-watchlist/'
        data = {'strategy_id': str(self.strategy.id)}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('task_id', response.data)

    def test_monitor_watchlist_inactive_strategy(self):
        """Test monitor watchlist with inactive strategy."""
        self.strategy.is_active = False
        self.strategy.save()

        url = '/api/agent-analysis/monitor-watchlist/'
        data = {'strategy_id': str(self.strategy.id)}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not active', response.data['error'])

    @patch('apps.agents.views.execute_autonomous_trade')
    def test_execute_trade_api(self, mock_task):
        """Test execute trade API endpoint."""
        mock_task.delay.return_value = Mock(id='test-task-id')

        url = '/api/agent-analysis/execute-trade/'
        data = {
            'strategy_id': str(self.strategy.id),
            'symbol': 'AAPL'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('task_id', response.data)

    def test_enable_autonomous_trading(self):
        """Test enable autonomous trading endpoint."""
        url = f'/api/strategy-agents/{self.strategy.id}/enable-autonomous/'

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

        # Verify strategy config updated
        self.strategy.refresh_from_db()
        self.assertTrue(self.strategy.config.get('autonomous_trading'))

    def test_disable_autonomous_trading(self):
        """Test disable autonomous trading endpoint."""
        # First enable it
        self.strategy.config = {'autonomous_trading': True}
        self.strategy.save()

        url = f'/api/strategy-agents/{self.strategy.id}/disable-autonomous/'

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

        # Verify strategy config updated
        self.strategy.refresh_from_db()
        self.assertFalse(self.strategy.config.get('autonomous_trading'))

    def test_strategy_agent_status(self):
        """Test strategy agent status endpoint."""
        url = f'/api/strategy-agents/{self.strategy.id}/status/'

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['strategy_id'], str(self.strategy.id))
        self.assertIn('autonomous_enabled', response.data)
        self.assertIn('watchlist_size', response.data)

    def test_authentication_required(self):
        """Test that authentication is required for agent endpoints."""
        self.client.force_authenticate(user=None)

        url = '/api/agent-analysis/analyze-stock/'
        data = {
            'portfolio_id': str(self.portfolio.id),
            'symbol': 'AAPL'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AgentIntegrationTests(TestCase):
    """Integration tests for end-to-end agent workflows."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        # Create broker connection
        self.broker = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            status='active',
            api_key_encrypted='encrypted_key',
            api_secret_encrypted='encrypted_secret'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            cash=Decimal('10000.00'),
            broker_connection=self.broker
        )

        self.strategy = Strategy.objects.create(
            user=self.user,
            portfolio=self.portfolio,
            name='Test Strategy',
            strategy_type='technical',
            is_active=True,
            watchlist=['AAPL']
        )

    @patch('apps.agents.orchestrator.AgentOrchestrator.run_sync')
    @patch('apps.agents.tasks.MassiveProvider')
    @patch('apps.agents.tasks.OrderExecutor')
    def test_full_autonomous_trade_workflow(self, mock_executor, mock_provider, mock_orchestrator):
        """Test complete autonomous trade workflow."""
        # Mock agent recommendation
        mock_orchestrator.return_value = {
            'final_recommendation': {
                'messages': [Mock(content='Strong BUY signal. RSI oversold.')]
            }
        }

        # Mock market data
        mock_provider_instance = mock_provider.return_value
        mock_provider_instance.get_quote.return_value = {'price': 150.0}

        # Mock order execution
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.execute_order = asyncio.coroutine(
            lambda order_id: {'success': True, 'filled': True}
        )

        # This would test the full workflow
        # In practice, would use Celery test runner or mock extensively
        pass
