import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

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
# FIX 1: Use correct field names matching the Portfolio model
portfolios_data = [
    {
        'name': 'Growth Portfolio',
        'portfolio_type': 'live',        # was: is_paper_trading / status
        'initial_capital': Decimal('50000.00'),
        'total_equity': Decimal('54230.50'),  # was: current_value
        'cash_balance': Decimal('12000.00'),
        'is_active': True,               # was: status: 'active'
    },
    {
        'name': 'Income Portfolio',
        'portfolio_type': 'live',
        'initial_capital': Decimal('30000.00'),
        'total_equity': Decimal('31450.00'),
        'cash_balance': Decimal('5000.00'),
        'is_active': True,
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
    # FIX 2: Use correct field names, correct types, and add required cost_basis
    positions_data = [
        {
            'portfolio': created_portfolios[0],
            'symbol': 'AAPL',
            'quantity': 100,                              # IntegerField, not Decimal
            'avg_entry_price': Decimal('175.50'),         # was: average_price
            'current_price': Decimal('182.30'),
            'side': 'long',                               # was: position_type
            'cost_basis': Decimal('175.50') * 100,        # required field
        },
        {
            'portfolio': created_portfolios[0],
            'symbol': 'MSFT',
            'quantity': 50,
            'avg_entry_price': Decimal('350.00'),
            'current_price': Decimal('368.50'),
            'side': 'long',
            'cost_basis': Decimal('350.00') * 50,
        },
        {
            'portfolio': created_portfolios[0],
            'symbol': 'NVDA',
            'quantity': 30,
            'avg_entry_price': Decimal('450.00'),
            'current_price': Decimal('475.20'),
            'side': 'long',
            'cost_basis': Decimal('450.00') * 30,
        },
        {
            'portfolio': created_portfolios[1],
            'symbol': 'VZ',
            'quantity': 200,
            'avg_entry_price': Decimal('40.00'),
            'current_price': Decimal('41.50'),
            'side': 'long',
            'cost_basis': Decimal('40.00') * 200,
        },
        {
            'portfolio': created_portfolios[1],
            'symbol': 'T',
            'quantity': 300,
            'avg_entry_price': Decimal('18.00'),
            'current_price': Decimal('17.80'),
            'side': 'long',
            'cost_basis': Decimal('18.00') * 300,
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
# FIX 3: 'value' is not a valid strategy_type choice — use 'custom' as fallback
strategies_data = [
    {
        'name': 'Momentum Trading',
        'description': 'Buy stocks with strong momentum and sell on weakness',
        'strategy_type': 'momentum',
        'status': 'active',
        'config': {
            'lookback_period': 20,
            'momentum_threshold': 0.05,
            'stop_loss': 0.02,
            'take_profit': 0.10,
        },
    },
    {
        'name': 'Value Investing',
        'description': 'Identify undervalued stocks with strong fundamentals',
        'strategy_type': 'custom',       # was: 'value' (not a valid choice)
        'status': 'active',
        'config': {
            'pe_ratio_max': 15,
            'pb_ratio_max': 2.5,
            'dividend_yield_min': 0.03,
        },
    },
    {
        'name': 'Mean Reversion',
        'description': 'Trade stocks that deviate from their mean',
        'strategy_type': 'mean_reversion',
        'status': 'inactive',
        'config': {
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
    # FIX 4: Use only valid Agent model fields and valid agent_type choices
    agents_data = [
        {
            'name': 'Tech Trader',
            'description': 'AI agent specializing in technology stocks',
            'agent_type': 'technical',    # was: 'trading' (invalid choice)
            'is_active': True,            # was: status: 'active'
            'strategy': created_strategies[0],
            'data_config': {              # was: configuration
                'symbols': ['AAPL', 'MSFT', 'NVDA', 'GOOGL'],
                'trading_hours': 'market',
                'max_trades_per_day': 5,
            },
        },
        {
            'name': 'Income Generator',
            'description': 'AI agent focused on dividend stocks',
            'agent_type': 'fundamental',  # was: 'income' (invalid choice)
            'is_active': True,
            'strategy': created_strategies[1],
            'data_config': {
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
    # FIX 5: Remove 'user' (no FK on Order), fix field names, use int for quantity
    orders_data = [
        {
            'portfolio': created_portfolios[0],
            'symbol': 'AAPL',
            'order_type': 'market',
            'side': 'buy',
            'quantity': 50,                           # IntegerField, not Decimal
            'status': 'filled',
            'filled_qty': 50,                         # was: filled_quantity
            'filled_avg_price': Decimal('180.25'),    # was: filled_price
        },
        {
            'portfolio': created_portfolios[0],
            'symbol': 'MSFT',
            'order_type': 'limit',
            'side': 'buy',
            'quantity': 25,
            'limit_price': Decimal('365.00'),         # was: price
            'status': 'filled',
            'filled_qty': 25,
            'filled_avg_price': Decimal('365.00'),
        },
        {
            'portfolio': created_portfolios[0],
            'symbol': 'NVDA',
            'order_type': 'market',
            'side': 'buy',
            'quantity': 20,
            'status': 'pending',
            'filled_qty': 0,                          # was: Decimal('0')
        },
    ]

    for order_data in orders_data:
        order, created = Order.objects.get_or_create(
            portfolio=order_data['portfolio'],
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