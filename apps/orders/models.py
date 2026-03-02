"""
Order and Trade models for ShefaAI Trading Platform.
"""
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid


class Order(models.Model):
    """Trading order."""

    ORDER_TYPE_CHOICES = [
        ('market', 'Market'),
        ('limit', 'Limit'),
        ('stop', 'Stop'),
        ('stop_limit', 'Stop Limit'),
        ('trailing_stop', 'Trailing Stop'),
    ]

    ORDER_SIDE_CHOICES = [
        ('buy', 'Buy'),
        ('sell', 'Sell'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('submitted', 'Submitted'),
        ('partially_filled', 'Partially Filled'),
        ('filled', 'Filled'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey('portfolios.Portfolio', on_delete=models.CASCADE, related_name='orders')
    strategy = models.ForeignKey(
        'strategies.Strategy',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )

    symbol = models.CharField('Symbol', max_length=20, db_index=True)
    order_type = models.CharField('Order Type', max_length=20, choices=ORDER_TYPE_CHOICES)
    side = models.CharField('Side', max_length=10, choices=ORDER_SIDE_CHOICES)

    # Quantity & Pricing
    quantity = models.IntegerField('Quantity', validators=[MinValueValidator(1)])
    limit_price = models.DecimalField(
        'Limit Price',
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )
    stop_price = models.DecimalField(
        'Stop Price',
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )
    filled_qty = models.IntegerField('Filled Quantity', default=0)
    filled_avg_price = models.DecimalField(
        'Filled Avg Price',
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True
    )

    # Status & Tracking
    status = models.CharField('Status', max_length=30, choices=STATUS_CHOICES, default='pending')
    broker_order_id = models.CharField('Broker Order ID', max_length=255, blank=True, db_index=True)

    # Approval (HITL)
    requires_approval = models.BooleanField('Requires Approval', default=False)
    approval_requested_at = models.DateTimeField('Approval Requested At', null=True, blank=True)
    approved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_orders'
    )
    approved_at = models.DateTimeField('Approved At', null=True, blank=True)
    rejection_reason = models.TextField('Rejection Reason', blank=True)

    # Agent Decision Reference
    agent_decision_id = models.UUIDField('Agent Decision ID', null=True, blank=True)
    agent_rationale = models.TextField('Agent Rationale', blank=True)
    agent_confidence = models.DecimalField(
        'Agent Confidence',
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Metadata
    error_message = models.TextField('Error Message', blank=True)
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)
    submitted_at = models.DateTimeField('Submitted to Broker', null=True, blank=True)
    filled_at = models.DateTimeField('Filled At', null=True, blank=True)

    class Meta:
        db_table = 'orders'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['portfolio', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['broker_order_id']),
            models.Index(fields=['symbol', '-created_at']),
        ]

    def __str__(self):
        return f'{self.side.upper()} {self.quantity} {self.symbol} @ {self.order_type}'


class Trade(models.Model):
    """Executed trade record."""

    TRADE_TYPE_CHOICES = [
        ('entry', 'Entry'),
        ('exit', 'Exit'),
        ('partial_exit', 'Partial Exit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey('portfolios.Portfolio', on_delete=models.CASCADE, related_name='trades')
    position = models.ForeignKey(
        'portfolios.Position',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trades'
    )
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, related_name='trades')
    strategy = models.ForeignKey(
        'strategies.Strategy',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trades'
    )

    symbol = models.CharField('Symbol', max_length=20, db_index=True)
    trade_type = models.CharField('Trade Type', max_length=20, choices=TRADE_TYPE_CHOICES)
    side = models.CharField('Side', max_length=10)

    # Execution Details
    quantity = models.IntegerField('Quantity')
    price = models.DecimalField('Price', max_digits=15, decimal_places=4)
    commission = models.DecimalField('Commission', max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_value = models.DecimalField('Total Value', max_digits=15, decimal_places=2)

    # P&L (for exit trades)
    realized_pnl = models.DecimalField(
        'Realized P&L',
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    realized_pnl_pct = models.DecimalField(
        'Realized P&L %',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )

    # Metadata
    broker_trade_id = models.CharField('Broker Trade ID', max_length=255, blank=True)
    executed_at = models.DateTimeField('Executed At', db_index=True)
    created_at = models.DateTimeField('Created At', auto_now_add=True)

    class Meta:
        db_table = 'trades'
        verbose_name = 'Trade'
        verbose_name_plural = 'Trades'
        ordering = ['-executed_at']
        indexes = [
            models.Index(fields=['portfolio', '-executed_at']),
            models.Index(fields=['symbol', '-executed_at']),
            models.Index(fields=['strategy', '-executed_at']),
        ]

    def __str__(self):
        return f'{self.side.upper()} {self.quantity} {self.symbol} @ ${self.price}'
