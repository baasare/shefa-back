import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from decimal import Decimal
from apps.users.models import User
from apps.portfolios.models import Portfolio, Position

email = 'atiemoasare@gmail.com'

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

# Create Portfolios with correct fields
portfolio1, created1 = Portfolio.objects.get_or_create(
    user=user,
    name='Growth Portfolio',
    defaults={
        'portfolio_type': 'live',
        'initial_capital': Decimal('50000.00'),
        'cash_balance': Decimal('12000.00'),
        'total_equity': Decimal('54230.50'),
        'daily_pnl': Decimal('1250.00'),
        'total_pnl': Decimal('4230.50'),
        'total_pnl_pct': Decimal('8.46'),
        'total_trades': 15,
        'winning_trades': 10,
        'losing_trades': 5,
        'win_rate': Decimal('66.67'),
        'max_drawdown': Decimal('5.20'),
        'is_active': True,
    }
)
print(f'✓ {"Created" if created1 else "Found"} portfolio: Growth Portfolio')

portfolio2, created2 = Portfolio.objects.get_or_create(
    user=user,
    name='Income Portfolio',
    defaults={
        'portfolio_type': 'live',
        'initial_capital': Decimal('30000.00'),
        'cash_balance': Decimal('5000.00'),
        'total_equity': Decimal('31450.00'),
        'daily_pnl': Decimal('150.00'),
        'total_pnl': Decimal('1450.00'),
        'total_pnl_pct': Decimal('4.83'),
        'total_trades': 8,
        'winning_trades': 6,
        'losing_trades': 2,
        'win_rate': Decimal('75.00'),
        'max_drawdown': Decimal('2.10'),
        'is_active': True,
    }
)
print(f'✓ {"Created" if created2 else "Found"} portfolio: Income Portfolio')

# Create Positions with correct fields
positions = [
    {
        'portfolio': portfolio1,
        'symbol': 'AAPL',
        'side': 'long',
        'quantity': 100,
        'avg_entry_price': Decimal('175.5000'),
        'current_price': Decimal('182.3000'),
        'cost_basis': Decimal('17550.00'),
        'current_value': Decimal('18230.00'),
        'unrealized_pnl': Decimal('680.00'),
        'unrealized_pnl_pct': Decimal('3.87'),
    },
    {
        'portfolio': portfolio1,
        'symbol': 'MSFT',
        'side': 'long',
        'quantity': 50,
        'avg_entry_price': Decimal('350.0000'),
        'current_price': Decimal('368.5000'),
        'cost_basis': Decimal('17500.00'),
        'current_value': Decimal('18425.00'),
        'unrealized_pnl': Decimal('925.00'),
        'unrealized_pnl_pct': Decimal('5.29'),
    },
    {
        'portfolio': portfolio1,
        'symbol': 'NVDA',
        'side': 'long',
        'quantity': 30,
        'avg_entry_price': Decimal('450.0000'),
        'current_price': Decimal('475.2000'),
        'cost_basis': Decimal('13500.00'),
        'current_value': Decimal('14256.00'),
        'unrealized_pnl': Decimal('756.00'),
        'unrealized_pnl_pct': Decimal('5.60'),
    },
    {
        'portfolio': portfolio2,
        'symbol': 'VZ',
        'side': 'long',
        'quantity': 200,
        'avg_entry_price': Decimal('40.0000'),
        'current_price': Decimal('41.5000'),
        'cost_basis': Decimal('8000.00'),
        'current_value': Decimal('8300.00'),
        'unrealized_pnl': Decimal('300.00'),
        'unrealized_pnl_pct': Decimal('3.75'),
    },
    {
        'portfolio': portfolio2,
        'symbol': 'T',
        'side': 'long',
        'quantity': 300,
        'avg_entry_price': Decimal('18.0000'),
        'current_price': Decimal('17.8000'),
        'cost_basis': Decimal('5400.00'),
        'current_value': Decimal('5340.00'),
        'unrealized_pnl': Decimal('-60.00'),
        'unrealized_pnl_pct': Decimal('-1.11'),
    },
]

for pos_data in positions:
    pos, created = Position.objects.get_or_create(
        portfolio=pos_data['portfolio'],
        symbol=pos_data['symbol'],
        defaults={k: v for k, v in pos_data.items() if k not in ['portfolio', 'symbol']}
    )
    print(f'✓ {"Created" if created else "Found"} position: {pos.symbol} in {pos.portfolio.name}')

print(f'\n✅ Successfully populated data for {user.email}!')
print(f'   - 2 Portfolios created')
print(f'   - 5 Positions created')
print(f'   - Dashboard is ready to view!')
