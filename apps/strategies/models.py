"""
Strategy models for ShefaFx Trading Platform.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import uuid


class Strategy(models.Model):
    """Trading strategy configuration."""

    STRATEGY_TYPE_CHOICES = [
        ('momentum', 'Momentum Breakout'),
        ('mean_reversion', 'Mean Reversion'),
        ('swing', 'Swing Trading'),
        ('trend_following', 'Trend Following'),
        ('custom', 'Custom Strategy'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('inactive', 'Inactive'),
        ('testing', 'Testing/Paper'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='strategies')
    portfolio = models.ForeignKey(
        'portfolios.Portfolio',
        on_delete=models.CASCADE,
        related_name='strategies',
        null=True,
        blank=True
    )

    name = models.CharField('Strategy Name', max_length=255)
    description = models.TextField('Description', blank=True)
    strategy_type = models.CharField('Type', max_length=50, choices=STRATEGY_TYPE_CHOICES)
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='inactive')

    # Strategy Configuration (JSON)
    config = models.JSONField('Configuration', default=dict)
    watchlist = models.JSONField('Watchlist (Symbols)', default=list)

    # Risk Parameters
    position_size_pct = models.DecimalField(
        'Position Size %',
        max_digits=5,
        decimal_places=2,
        default=Decimal('2.00'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('100.00'))]
    )
    max_positions = models.IntegerField('Max Open Positions', default=5)
    max_daily_loss_pct = models.DecimalField(
        'Max Daily Loss %',
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00')
    )

    # Entry/Exit Rules
    entry_rules = models.JSONField('Entry Rules', default=dict)
    exit_rules = models.JSONField('Exit Rules', default=dict)

    # Performance Tracking
    total_trades = models.IntegerField('Total Trades', default=0)
    winning_trades = models.IntegerField('Winning Trades', default=0)
    win_rate = models.DecimalField('Win Rate %', max_digits=5, decimal_places=2, default=Decimal('0.00'))
    total_pnl = models.DecimalField('Total P&L', max_digits=15, decimal_places=2, default=Decimal('0.00'))
    sharpe_ratio = models.DecimalField(
        'Sharpe Ratio',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)
    activated_at = models.DateTimeField('Last Activated', null=True, blank=True)

    class Meta:
        db_table = 'strategies'
        verbose_name = 'Strategy'
        verbose_name_plural = 'Strategies'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.user.email} - {self.name}'


class Backtest(models.Model):
    """Backtest results for strategies."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name='backtests')

    start_date = models.DateField('Start Date')
    end_date = models.DateField('End Date')
    initial_capital = models.DecimalField('Initial Capital', max_digits=15, decimal_places=2)
    final_capital = models.DecimalField('Final Capital', max_digits=15, decimal_places=2, null=True, blank=True)

    # Performance Metrics
    total_return = models.DecimalField('Total Return %', max_digits=10, decimal_places=4, null=True, blank=True)
    annual_return = models.DecimalField('Annual Return %', max_digits=10, decimal_places=4, null=True, blank=True)
    sharpe_ratio = models.DecimalField('Sharpe Ratio', max_digits=10, decimal_places=4, null=True, blank=True)
    sortino_ratio = models.DecimalField('Sortino Ratio', max_digits=10, decimal_places=4, null=True, blank=True)
    max_drawdown = models.DecimalField('Max Drawdown %', max_digits=10, decimal_places=4, null=True, blank=True)

    # Trading Stats
    total_trades = models.IntegerField('Total Trades', default=0)
    winning_trades = models.IntegerField('Winning Trades', default=0)
    losing_trades = models.IntegerField('Losing Trades', default=0)
    win_rate = models.DecimalField('Win Rate %', max_digits=5, decimal_places=2, default=Decimal('0.00'))
    avg_trade_pnl = models.DecimalField('Avg Trade P&L', max_digits=15, decimal_places=2, null=True, blank=True)

    # Detailed Results
    results = models.JSONField('Detailed Results', null=True, blank=True)
    equity_curve = models.JSONField('Equity Curve', null=True, blank=True)

    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField('Error Message', blank=True)

    created_at = models.DateTimeField('Created At', auto_now_add=True)
    completed_at = models.DateTimeField('Completed At', null=True, blank=True)

    class Meta:
        db_table = 'backtests'
        verbose_name = 'Backtest'
        verbose_name_plural = 'Backtests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['strategy', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.strategy.name} Backtest ({self.start_date} to {self.end_date})'
