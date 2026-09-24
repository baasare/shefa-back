import asyncio
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.brokers.models import BrokerConnection
from apps.orders.execution import OrderExecutionEngine, OrderExecutionError
from apps.orders.models import Order
from apps.portfolios.models import Portfolio


User = get_user_model()


class ExecutionModeBoundaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='paper@example.com', password='test-pass')
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Paper account',
            portfolio_type='paper',
            initial_capital=Decimal('10000.00'),
            cash_balance=Decimal('10000.00'),
            total_equity=Decimal('10000.00'),
        )

    def _connection(self, *, broker, paper, portfolio=None, user=None):
        return BrokerConnection.objects.create(
            user=user or self.user,
            portfolio=portfolio if portfolio is not None else self.portfolio,
            broker=broker,
            status='active',
            is_paper_trading=paper,
            api_key_encrypted='encrypted-key',
            api_secret_encrypted='encrypted-secret',
        )

    def test_paper_portfolio_cannot_submit_through_live_connection(self):
        live_connection = self._connection(broker='alpaca', paper=False)
        engine = OrderExecutionEngine(self.user, live_connection)

        with patch('apps.orders.execution.get_broker_client') as get_client:
            with self.assertRaisesMessage(
                OrderExecutionError,
                'Paper portfolios may only use an Alpaca paper connection',
            ):
                asyncio.run(engine.submit_order(
                    portfolio=self.portfolio,
                    symbol='AAPL',
                    quantity=1,
                    side='buy',
                ))

        get_client.assert_not_called()
        self.assertEqual(Order.objects.count(), 0)

    def test_paper_portfolio_does_not_fall_back_to_users_live_connection(self):
        self._connection(broker='alpaca', paper=False)
        engine = OrderExecutionEngine(self.user)

        with patch('apps.orders.execution.get_broker_client') as get_client:
            with self.assertRaisesMessage(
                OrderExecutionError,
                'Paper portfolios may only use an Alpaca paper connection',
            ):
                asyncio.run(engine.submit_order(
                    portfolio=self.portfolio,
                    symbol='AAPL',
                    quantity=1,
                    side='buy',
                ))

        get_client.assert_not_called()
        self.assertEqual(Order.objects.count(), 0)

    def test_live_connection_attached_to_another_portfolio_is_rejected(self):
        other_portfolio = Portfolio.objects.create(
            user=self.user,
            name='Other paper account',
            portfolio_type='paper',
            initial_capital=Decimal('10000.00'),
            cash_balance=Decimal('10000.00'),
            total_equity=Decimal('10000.00'),
        )
        live_connection = self._connection(
            broker='alpaca', paper=False, portfolio=other_portfolio
        )
        engine = OrderExecutionEngine(self.user, live_connection)

        with patch('apps.orders.execution.get_broker_client') as get_client:
            with self.assertRaisesMessage(
                OrderExecutionError,
                'Broker connection is not attached to this portfolio',
            ):
                asyncio.run(engine.submit_order(
                    portfolio=self.portfolio,
                    symbol='AAPL',
                    quantity=1,
                    side='buy',
                ))

        get_client.assert_not_called()
        self.assertEqual(Order.objects.count(), 0)

    def test_live_portfolios_are_disabled(self):
        self.portfolio.portfolio_type = 'live'
        self.portfolio.save(update_fields=['portfolio_type'])
        live_connection = self._connection(broker='alpaca', paper=False)
        engine = OrderExecutionEngine(self.user, live_connection)

        with patch('apps.orders.execution.get_broker_client') as get_client:
            with self.assertRaisesMessage(OrderExecutionError, 'Live trading is disabled'):
                asyncio.run(engine.submit_order(
                    portfolio=self.portfolio,
                    symbol='AAPL',
                    quantity=1,
                    side='buy',
                ))

        get_client.assert_not_called()
        self.assertEqual(Order.objects.count(), 0)
