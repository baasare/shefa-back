import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.utils import timezone
from decimal import Decimal
from apps.users.models import User, UserProfile
from apps.portfolios.models import Portfolio, Position
from apps.strategies.models import Strategy
from apps.agents.models import Agent
from apps.orders.models import Order

email = 'asarebernard98@gmail.com'

try:
    user = User.objects.get(email=email)
    print(f'✓ Found user: {user.email}')
except User.DoesNotExist:
    print(f'✗ User {email} not found')
    exit(1)

# Mark onboarding as completed
user.onboarding_completed = True
user.save()
print('✓ Marked onboarding as completed')

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
    print('✓ Created user profile')
else:
    print('✓ User profile already exists')

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
        print(f'✓ Created portfolio: {portfolio.name}')
    else:
        print(f'✓ Portfolio exists: {portfolio.name}')

# Create Positions
if len(created_portfolios) >= 2:
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
            print(f'✓ Created position: {position.symbol} in {position.portfolio.name}')
        else:
            print(f'✓ Position exists: {position.symbol}')

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
        print(f'✓ Created strategy: {strategy.name}')
    else:
        print(f'✓ Strategy exists: {strategy.name}')

# Create Agents
if len(created_portfolios) >= 2 and len(created_strategies) >= 2:
    agents_data = [
        {
            'name': 'Tech Trader',
            'description': 'AI agent specializing in technology stocks',
            'agent_type': 'trading',
            'status': 'active',
            'portfolio': created_portfolios[0],
            'strategy': created_strategies[0],
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
            'strategy': created_strategies[1],
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
            print(f'✓ Created agent: {agent.name}')
        else:
            print(f'✓ Agent exists: {agent.name}')

# Create Orders
if len(created_portfolios) >= 1:
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

    for i, order_data in enumerate(orders_data):
        # Use a unique combination for get_or_create to avoid conflicts
        order, created = Order.objects.get_or_create(
            user=order_data['user'],
            symbol=order_data['symbol'],
            side=order_data['side'],
            quantity=order_data['quantity'],
            status=order_data['status'],
            defaults=order_data
        )
        if created:
            print(f'✓ Created order: {order.symbol} {order.side}')
        else:
            print(f'✓ Order exists: {order.symbol} {order.side}')

print(f'\n✓ Successfully populated data for {user.email}!')
print(f'  - Portfolios: {len(created_portfolios)}')
print(f'  - Strategies: {len(created_strategies)}')
print(f'  - Dashboard is now ready to view!')
