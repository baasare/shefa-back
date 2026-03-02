"""
Portfolio models for ShefaAI Trading Platform.
"""
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid


class Portfolio(models.Model):
    """User's trading portfolio."""

    PORTFOLIO_TYPE_CHOICES = [
        ('live', 'Live Trading'),
        ('paper', 'Paper Trading'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='portfolios'
    )

    name = models.CharField('Portfolio Name', max_length=255)
    portfolio_type = models.CharField(
        'Type',
        max_length=20,
        choices=PORTFOLIO_TYPE_CHOICES,
        default='paper'
    )

    # Balances
    initial_capital = models.DecimalField(
        'Initial Capital',
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    cash_balance = models.DecimalField(
        'Cash Balance',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_equity = models.DecimalField(
        'Total Equity',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # P&L Tracking
    daily_pnl = models.DecimalField(
        'Daily P&L',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_pnl = models.DecimalField(
        'Total P&L',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_pnl_pct = models.DecimalField(
        'Total P&L %',
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.00')
    )

    # Performance Metrics
    total_trades = models.IntegerField('Total Trades', default=0)
    winning_trades = models.IntegerField('Winning Trades', default=0)
    losing_trades = models.IntegerField('Losing Trades', default=0)
    win_rate = models.DecimalField(
        'Win Rate %',
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Risk Metrics
    max_drawdown = models.DecimalField(
        'Max Drawdown %',
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.00')
    )
    sharpe_ratio = models.DecimalField(
        'Sharpe Ratio',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )

    # Status
    is_active = models.BooleanField('Active', default=True)

    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)

    class Meta:
        db_table = 'portfolios'
        verbose_name = 'Portfolio'
        verbose_name_plural = 'Portfolios'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['portfolio_type', 'is_active']),
        ]
        unique_together = [['user', 'name']]

    def __str__(self):
        return f'{self.user.email} - {self.name}'

    def calculate_equity(self):
        """Calculate total portfolio equity."""
        positions_value = self.positions.aggregate(
            total=models.Sum(
                models.F('quantity') * models.F('current_price'),
                output_field=models.DecimalField()
            )
        )['total'] or Decimal('0.00')

        self.total_equity = self.cash_balance + positions_value
        self.save(update_fields=['total_equity', 'updated_at'])
        return self.total_equity

    def calculate_pnl(self):
        """Calculate total P&L."""
        self.total_pnl = self.total_equity - self.initial_capital
        if self.initial_capital > 0:
            self.total_pnl_pct = (self.total_pnl / self.initial_capital) * 100
        self.save(update_fields=['total_pnl', 'total_pnl_pct', 'updated_at'])

    def update_win_rate(self):
        """Update win rate based on trades."""
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100
            self.save(update_fields=['win_rate', 'updated_at'])


class Position(models.Model):
    """Open trading position."""

    POSITION_SIDE_CHOICES = [
        ('long', 'Long'),
        ('short', 'Short'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name='positions'
    )
    strategy = models.ForeignKey(
        'strategies.Strategy',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='positions'
    )

    symbol = models.CharField('Symbol', max_length=20, db_index=True)
    side = models.CharField(
        'Side',
        max_length=10,
        choices=POSITION_SIDE_CHOICES,
        default='long'
    )

    # Position Details
    quantity = models.IntegerField('Quantity', validators=[MinValueValidator(1)])
    avg_entry_price = models.DecimalField(
        'Avg Entry Price',
        max_digits=15,
        decimal_places=4
    )
    current_price = models.DecimalField(
        'Current Price',
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )

    # Cost Basis
    cost_basis = models.DecimalField(
        'Cost Basis',
        max_digits=15,
        decimal_places=2
    )
    current_value = models.DecimalField(
        'Current Value',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # P&L
    unrealized_pnl = models.DecimalField(
        'Unrealized P&L',
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    unrealized_pnl_pct = models.DecimalField(
        'Unrealized P&L %',
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.00')
    )

    # Risk Management
    stop_loss_price = models.DecimalField(
        'Stop Loss',
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )
    take_profit_price = models.DecimalField(
        'Take Profit',
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )
    trailing_stop_enabled = models.BooleanField('Trailing Stop', default=False)
    trailing_stop_pct = models.DecimalField(
        'Trailing Stop %',
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Metadata
    opened_at = models.DateTimeField('Opened At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)

    class Meta:
        db_table = 'positions'
        verbose_name = 'Position'
        verbose_name_plural = 'Positions'
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['portfolio', 'symbol']),
            models.Index(fields=['symbol', '-opened_at']),
        ]

    def __str__(self):
        return f'{self.symbol} - {self.quantity} shares @ ${self.avg_entry_price}'

    def update_current_value(self, current_price):
        """Update position value and P&L based on current price."""
        self.current_price = current_price
        self.current_value = Decimal(str(self.quantity)) * current_price

        if self.side == 'long':
            self.unrealized_pnl = self.current_value - self.cost_basis
        else:  # short
            self.unrealized_pnl = self.cost_basis - self.current_value

        if self.cost_basis > 0:
            self.unrealized_pnl_pct = (self.unrealized_pnl / self.cost_basis) * 100

        self.save(update_fields=[
            'current_price', 'current_value',
            'unrealized_pnl', 'unrealized_pnl_pct', 'updated_at'
        ])


class PortfolioSnapshot(models.Model):
    """Daily portfolio snapshots for performance tracking."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name='snapshots'
    )

    snapshot_date = models.DateField('Snapshot Date', db_index=True)
    total_equity = models.DecimalField('Total Equity', max_digits=15, decimal_places=2)
    cash_balance = models.DecimalField('Cash Balance', max_digits=15, decimal_places=2)
    positions_value = models.DecimalField('Positions Value', max_digits=15, decimal_places=2)
    daily_pnl = models.DecimalField('Daily P&L', max_digits=15, decimal_places=2)
    cumulative_pnl = models.DecimalField('Cumulative P&L', max_digits=15, decimal_places=2)

    # Metrics
    total_trades = models.IntegerField('Total Trades', default=0)
    win_rate = models.DecimalField('Win Rate %', max_digits=5, decimal_places=2, default=Decimal('0.00'))
    sharpe_ratio = models.DecimalField('Sharpe Ratio', max_digits=10, decimal_places=4, null=True, blank=True)

    created_at = models.DateTimeField('Created At', auto_now_add=True)

    class Meta:
        db_table = 'portfolio_snapshots'
        verbose_name = 'Portfolio Snapshot'
        verbose_name_plural = 'Portfolio Snapshots'
        ordering = ['-snapshot_date']
        indexes = [
            models.Index(fields=['portfolio', '-snapshot_date']),
        ]
        unique_together = [['portfolio', 'snapshot_date']]

    def __str__(self):
        return f'{self.portfolio.name} - {self.snapshot_date}'
