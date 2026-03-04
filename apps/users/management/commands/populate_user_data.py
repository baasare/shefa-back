"""
Management command to populate sample data for a user
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from apps.users.models import User, UserProfile
from apps.portfolios.models import Portfolio, Position
from apps.strategies.models import Strategy
from apps.agents.models import Agent
from apps.orders.models import Order
import random


class Command(BaseCommand):
    help = 'Populate sample data for a user'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='User email address')

    def handle(self, *args, **options):
        email = options['email']
        
        try:
            user = User.objects.get(email=email)
            self.stdout.write(self.style.SUCCESS(f'Found user: {user.email}'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {email} not found'))
            return

        # Mark onboarding as completed
        user.onboarding_completed = True
        user.save()
        self.stdout.write(self.style.SUCCESS('Marked onboarding as completed'))

        # Create UserProfile if doesn't exist
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'investment_goals': 'Long-term wealth building and retirement planning',
                'time_horizon': '10+ years',
                'preferred_asset_classes': ['stocks', 'etfs'],
                'default_paper_trading': False,
                'max_daily_loss_pct': Decimal('5.00'),
                'max_position_size_pct': Decimal('10.00'),
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Created user profile'))

        # Create Portfolios
        portfolios_data = [
            {
                'name': 'Growth Portfolio',
                'description': 'Aggressive growth focused on tech stocks',
                'initial_capital': Decimal('50000.00'),
                'current_value': Decimal('54230.50'),
                'cash_balance': Decimal('12000.00'),
                'is_paper_trading': False,
                'status': 'active',
            },
            {
                'name': 'Income Portfolio',
                'description': 'Dividend-focused portfolio for steady income',
                'initial_capital': Decimal('30000.00'),
                'current_value': Decimal('31450.00'),
                'cash_balance': Decimal('5000.00'),
                'is_paper_trading': False,
                'status': 'active',
            },
        ]

        created_portfolios = []
        for portfolio_data in portfolios_data:
            portfolio, created = Portfolio.objects.get_or_create(
                user=user,
                name=portfolio_data['name'],
                defaults=portfolio_data
            )
            created_portfolios.append(portfolio)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created portfolio: {portfolio.name}'))

        # Create Positions
        positions_data = [
            {
                'portfolio': created_portfolios[0],
                'symbol': 'AAPL',
                'quantity': Decimal('100'),
                'average_price': Decimal('175.50'),
                'current_price': Decimal('182.30'),
                'position_type': 'long',
                'status': 'open',
            },
            {
                'portfolio': created_portfolios[0],
                'symbol': 'MSFT',
                'quantity': Decimal('50'),
                'average_price': Decimal('350.00'),
                'current_price': Decimal('368.50'),
                'position_type': 'long',
                'status': 'open',
            },
            {
                'portfolio': created_portfolios[0],
                'symbol': 'NVDA',
                'quantity': Decimal('30'),
                'average_price': Decimal('450.00'),
                'current_price': Decimal('475.20'),
                'position_type': 'long',
                'status': 'open',
            },
            {
                'portfolio': created_portfolios[1],
                'symbol': 'VZ',
                'quantity': Decimal('200'),
                'average_price': Decimal('40.00'),
                'current_price': Decimal('41.50'),
                'position_type': 'long',
                'status': 'open',
            },
            {
                'portfolio': created_portfolios[1],
                'symbol': 'T',
                'quantity': Decimal('300'),
                'average_price': Decimal('18.00'),
                'current_price': Decimal('17.80'),
                'position_type': 'long',
                'status': 'open',
            },
        ]

        for position_data in positions_data:
            position, created = Position.objects.get_or_create(
                portfolio=position_data['portfolio'],
                symbol=position_data['symbol'],
                defaults=position_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created position: {position.symbol}'))

        # Create Strategies
        strategies_data = [
            {
                'name': 'Momentum Trading',
                'description': 'Buy stocks with strong momentum and sell on weakness',
                'strategy_type': 'momentum',
                'is_active': True,
                'parameters': {
                    'lookback_period': 20,
                    'momentum_threshold': 0.05,
                    'stop_loss': 0.02,
                    'take_profit': 0.10,
                },
            },
            {
                'name': 'Value Investing',
                'description': 'Identify undervalued stocks with strong fundamentals',
                'strategy_type': 'value',
                'is_active': True,
                'parameters': {
                    'pe_ratio_max': 15,
                    'pb_ratio_max': 2.5,
                    'dividend_yield_min': 0.03,
                },
            },
            {
                'name': 'Mean Reversion',
                'description': 'Trade stocks that deviate from their mean',
                'strategy_type': 'mean_reversion',
                'is_active': False,
                'parameters': {
                    'std_dev_threshold': 2,
                    'lookback_period': 30,
                },
            },
        ]

        created_strategies = []
        for strategy_data in strategies_data:
            strategy, created = Strategy.objects.get_or_create(
                user=user,
                name=strategy_data['name'],
                defaults=strategy_data
            )
            created_strategies.append(strategy)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created strategy: {strategy.name}'))

        # Create Agents
        agents_data = [
            {
                'name': 'Tech Trader',
                'description': 'AI agent specializing in technology stocks',
                'agent_type': 'trading',
                'status': 'active',
                'portfolio': created_portfolios[0],
                'strategy': created_strategies[0] if created_strategies else None,
                'risk_level': 'moderate',
                'max_position_size': Decimal('5000.00'),
                'configuration': {
                    'symbols': ['AAPL', 'MSFT', 'NVDA', 'GOOGL'],
                    'trading_hours': 'market',
                    'max_trades_per_day': 5,
                },
            },
            {
                'name': 'Income Generator',
                'description': 'AI agent focused on dividend stocks',
                'agent_type': 'income',
                'status': 'active',
                'portfolio': created_portfolios[1],
                'strategy': created_strategies[1] if len(created_strategies) > 1 else None,
                'risk_level': 'conservative',
                'max_position_size': Decimal('3000.00'),
                'configuration': {
                    'min_dividend_yield': 0.04,
                    'sector_diversification': True,
                },
            },
        ]

        for agent_data in agents_data:
            agent, created = Agent.objects.get_or_create(
                user=user,
                name=agent_data['name'],
                defaults=agent_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created agent: {agent.name}'))

        # Create Orders
        orders_data = [
            {
                'user': user,
                'portfolio': created_portfolios[0],
                'symbol': 'AAPL',
                'order_type': 'market',
                'side': 'buy',
                'quantity': Decimal('50'),
                'price': Decimal('180.00'),
                'status': 'filled',
                'filled_quantity': Decimal('50'),
                'filled_price': Decimal('180.25'),
            },
            {
                'user': user,
                'portfolio': created_portfolios[0],
                'symbol': 'MSFT',
                'order_type': 'limit',
                'side': 'buy',
                'quantity': Decimal('25'),
                'price': Decimal('365.00'),
                'status': 'filled',
                'filled_quantity': Decimal('25'),
                'filled_price': Decimal('365.00'),
            },
            {
                'user': user,
                'portfolio': created_portfolios[0],
                'symbol': 'NVDA',
                'order_type': 'market',
                'side': 'buy',
                'quantity': Decimal('20'),
                'price': Decimal('470.00'),
                'status': 'pending',
                'filled_quantity': Decimal('0'),
            },
        ]

        for order_data in orders_data:
            order, created = Order.objects.get_or_create(
                user=order_data['user'],
                symbol=order_data['symbol'],
                side=order_data['side'],
                quantity=order_data['quantity'],
                defaults=order_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created order: {order.symbol} {order.side}'))

        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully populated data for {user.email}!'))
        self.stdout.write(self.style.SUCCESS(f'Created {len(created_portfolios)} portfolios'))
        self.stdout.write(self.style.SUCCESS(f'Created {len(positions_data)} positions'))
        self.stdout.write(self.style.SUCCESS(f'Created {len(created_strategies)} strategies'))
        self.stdout.write(self.style.SUCCESS(f'Created {len(agents_data)} agents'))
        self.stdout.write(self.style.SUCCESS(f'Created {len(orders_data)} orders'))
