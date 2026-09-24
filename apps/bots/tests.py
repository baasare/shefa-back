from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bots.models import Bot, BotEvent, BotRun
from apps.brokers.models import BrokerConnection
from apps.orders.models import Order
from apps.portfolios.models import Portfolio


User = get_user_model()


@override_settings(ALLOWED_HOSTS=['*'])
class PaperBotAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='bot@example.com', password='test-pass')
        self.other_user = User.objects.create_user(email='other@example.com', password='test-pass')
        self.client = APIClient()
        self.client.defaults['HTTP_HOST'] = 'api.testserver'
        self.client.force_authenticate(self.user)
        self.payload = {
            'name': 'Starter bot',
            'idea': 'Look for a gentle upward trend and avoid trading when the data is unclear.',
            'symbols': ['AAPL', 'MSFT'],
            'max_order_value': '100.00',
            'max_open_positions': 3,
            'daily_loss_limit_pct': '2.00',
            'run_frequency_minutes': 15,
        }

    def create_bot(self):
        response = self.client.post('/v1/bots/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return Bot.objects.get(id=response.data['id'])

    def connect_paper(self, bot):
        return BrokerConnection.objects.create(
            user=self.user,
            portfolio=bot.portfolio,
            broker='alpaca_paper',
            status='active',
            is_paper_trading=True,
            api_key_encrypted='encrypted-key',
            api_secret_encrypted='encrypted-secret',
        )

    def test_create_bot_creates_default_paper_portfolio(self):
        response = self.client.post('/v1/bots/', self.payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        portfolio = Portfolio.objects.get(user=self.user, name='Paper Trading')
        self.assertEqual(portfolio.portfolio_type, 'paper')
        self.assertEqual(portfolio.initial_capital, Decimal('100000.00'))
        self.assertEqual(str(response.data['portfolio']), str(portfolio.id))
        self.assertEqual(response.data['portfolio_mode'], 'paper')
        self.assertEqual(BotEvent.objects.filter(bot_id=response.data['id'], event_type='bot_created').count(), 1)

    def test_create_rejects_non_stock_symbols_and_excessive_risk(self):
        payload = {**self.payload, 'symbols': ['BTC/USD']}
        response = self.client.post('/v1/bots/', payload, format='json')
        self.assertEqual(response.status_code, 400)

        payload = {**self.payload, 'max_order_value': '1001'}
        response = self.client.post('/v1/bots/', payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_user_cannot_read_another_users_bot(self):
        bot = self.create_bot()
        other_client = APIClient()
        other_client.defaults['HTTP_HOST'] = 'api.testserver'
        other_client.force_authenticate(self.other_user)

        response = other_client.get(f'/v1/bots/{bot.id}/')

        self.assertEqual(response.status_code, 404)

    def test_start_requires_verified_paper_connection(self):
        bot = self.create_bot()

        response = self.client.post(f'/v1/bots/{bot.id}/start/', {}, format='json')

        self.assertEqual(response.status_code, 409)
        bot.refresh_from_db()
        self.assertEqual(bot.status, 'draft')

    def test_start_and_run_are_explicitly_paper_and_enqueued_once(self):
        bot = self.create_bot()
        self.connect_paper(bot)

        started = self.client.post(f'/v1/bots/{bot.id}/start/', {}, format='json')
        self.assertEqual(started.status_code, 200, started.data)
        self.assertEqual(started.data['status'], 'active')

        with patch('apps.bots.views.run_paper_bot.apply_async') as enqueue:
            queued = self.client.post(f'/v1/bots/{bot.id}/run/', {}, format='json')
            self.assertEqual(queued.status_code, 202, queued.data)
            enqueue.assert_called_once_with(args=[queued.data['id']])

            duplicate = self.client.post(f'/v1/bots/{bot.id}/run/', {}, format='json')
            self.assertEqual(duplicate.status_code, 409)
            enqueue.assert_called_once()

        self.assertTrue(BotEvent.objects.filter(bot=bot, event_type='run_queued').exists())

    def test_queue_unavailable_fails_closed_and_records_error(self):
        bot = self.create_bot()
        self.connect_paper(bot)
        self.client.post(f'/v1/bots/{bot.id}/start/', {}, format='json')

        with patch('apps.bots.views.run_paper_bot.apply_async', side_effect=RuntimeError('redis unavailable')):
            response = self.client.post(f'/v1/bots/{bot.id}/run/', {}, format='json')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(BotRun.objects.filter(bot=bot, status='failed').count(), 1)
        self.assertTrue(BotEvent.objects.filter(bot=bot, event_type='error').exists())

    def test_langchain_draft_is_available_only_when_ai_configured(self):
        from apps.bots.llm import BotAIError

        with patch('apps.bots.views.draft_bot', side_effect=BotAIError('AI is not configured.')):
            response = self.client.post('/v1/bots/draft/', {'idea': 'Buy a small amount when the trend improves.'}, format='json')

        self.assertEqual(response.status_code, 503)
        self.assertIn('AI is not configured', response.data['detail'])

    def test_pause_and_stop_prevent_future_runs(self):
        bot = self.create_bot()
        self.connect_paper(bot)
        self.client.post(f'/v1/bots/{bot.id}/start/', {}, format='json')

        paused = self.client.post(f'/v1/bots/{bot.id}/pause/', {}, format='json')
        self.assertEqual(paused.data['status'], 'paused')
        bot.refresh_from_db()
        self.assertIsNone(bot.next_run_at)

        stopped = self.client.post(f'/v1/bots/{bot.id}/stop/', {}, format='json')
        self.assertEqual(stopped.data['status'], 'stopped')


class PaperBotExecutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='runner@example.com', password='test-pass')
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Paper Trading',
            portfolio_type='paper',
            initial_capital=Decimal('10000'),
            cash_balance=Decimal('10000'),
            total_equity=Decimal('10000'),
        )
        self.bot = Bot.objects.create(
            user=self.user,
            portfolio=self.portfolio,
            name='Test bot',
            idea='Only buy if the price trend is positive; otherwise hold.',
            symbols=['AAPL'],
            max_order_value=Decimal('100'),
            status='active',
        )
        self.connection = BrokerConnection.objects.create(
            user=self.user,
            portfolio=self.portfolio,
            broker='alpaca_paper',
            status='active',
            is_paper_trading=True,
            api_key_encrypted='encrypted-key',
            api_secret_encrypted='encrypted-secret',
        )
        self.run = BotRun.objects.create(bot=self.bot)

    def _client(self, *, paper=True, open_market=True, quote_time=None):
        from unittest.mock import AsyncMock, Mock

        client = Mock()
        client.paper = paper
        client.get_account_info = AsyncMock(return_value={
            'status': 'ACTIVE',
            'trading_blocked': False,
            'last_equity': Decimal('10000'),
            'portfolio_value': Decimal('10000'),
            'buying_power': Decimal('500'),
        })
        client.get_positions = AsyncMock(return_value=[])
        client.get_market_clock.return_value = {'is_open': open_market}
        client.get_quote = AsyncMock(return_value={
            'symbol': 'AAPL',
            'bid': Decimal('99.90'),
            'ask': Decimal('100.00'),
            'timestamp': quote_time or timezone.now(),
        })
        client.get_daily_bars = AsyncMock(return_value=[{'close': '100'}] * 5)
        client.submit_order = AsyncMock(return_value={
            'broker_order_id': 'alpaca-paper-order-1',
            'status': 'submitted',
            'submitted_at': timezone.now(),
        })
        return client

    def test_run_submits_only_bounded_paper_order_and_persists_events(self):
        from apps.bots.llm import TradeSuggestion
        from apps.bots.services import execute_paper_run

        client = self._client()
        with patch('apps.bots.services.get_broker_client', return_value=client), patch(
            'apps.bots.services.suggest_trade',
            return_value=TradeSuggestion(action='buy', explanation='The supplied trend data is positive.'),
        ):
            run = execute_paper_run(self.run.id)

        self.assertEqual(run.status, 'completed')
        order = Order.objects.get(portfolio=self.portfolio)
        self.assertEqual(order.symbol, 'AAPL')
        self.assertEqual(order.side, 'buy')
        self.assertEqual(order.quantity, 1)
        self.assertEqual(order.status, 'submitted')
        client.submit_order.assert_awaited_once()
        self.assertEqual(client.submit_order.await_args.kwargs['client_order_id'], f'sf3-{self.run.id.hex[:28]}-AAPL')
        self.assertTrue(BotEvent.objects.filter(bot=self.bot, event_type='order_created').exists())
        self.assertTrue(BotEvent.objects.filter(bot=self.bot, event_type='run_completed').exists())

    def test_live_client_and_stale_quote_never_submit(self):
        from datetime import timedelta
        from apps.bots.llm import TradeSuggestion
        from apps.bots.services import execute_paper_run

        live_client = self._client(paper=False)
        with patch('apps.bots.services.get_broker_client', return_value=live_client):
            run = execute_paper_run(self.run.id)
        self.assertEqual(run.status, 'failed')
        live_client.submit_order.assert_not_awaited()

        Bot.objects.filter(id=self.bot.id).update(status='active')
        self.run.status = 'queued'
        self.run.save(update_fields=['status'])
        stale_client = self._client(quote_time=timezone.now() - timedelta(minutes=6))
        with patch('apps.bots.services.get_broker_client', return_value=stale_client), patch(
            'apps.bots.services.suggest_trade',
            return_value=TradeSuggestion(action='buy', explanation='Example.'),
        ):
            run = execute_paper_run(self.run.id)
        self.assertEqual(run.status, 'completed')
        stale_client.submit_order.assert_not_awaited()
        self.assertEqual(Order.objects.filter(portfolio=self.portfolio).count(), 0)

    def test_closed_market_creates_no_order_and_completes_run(self):
        from apps.bots.services import execute_paper_run

        client = self._client(open_market=False)
        with patch('apps.bots.services.get_broker_client', return_value=client):
            run = execute_paper_run(self.run.id)
        self.assertEqual(run.status, 'completed')
        self.assertEqual(Order.objects.filter(portfolio=self.portfolio).count(), 0)
        client.get_quote.assert_not_awaited()

    def test_pause_during_analysis_prevents_order_submission(self):
        from apps.bots.llm import TradeSuggestion
        from apps.bots.services import execute_paper_run

        client = self._client()

        def pause_then_buy(**kwargs):
            Bot.objects.filter(id=self.bot.id).update(status='paused')
            return TradeSuggestion(action='buy', explanation='A supplied signal looks positive.')

        with patch('apps.bots.services.get_broker_client', return_value=client), patch(
            'apps.bots.services.suggest_trade', side_effect=pause_then_buy,
        ):
            run = execute_paper_run(self.run.id)

        self.assertEqual(run.status, 'completed')
        client.submit_order.assert_not_awaited()
        self.assertFalse(Order.objects.filter(portfolio=self.portfolio).exists())

    def test_sale_quantity_obeys_order_value_cap(self):
        from apps.bots.services import _order_quantity

        quantity = _order_quantity(
            'sell', Decimal('100'), {'bid': Decimal('50'), 'ask': Decimal('51')},
            {'quantity': 20},
        )

        self.assertEqual(quantity, 2)
