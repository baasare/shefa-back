"""
Market Data models for ShefaAI Trading Platform.
"""
import uuid
from django.db import models


class Quote(models.Model):
    """Real-time and historical market quotes (OHLCV data)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField('Symbol', max_length=20, db_index=True)
    timestamp = models.DateTimeField('Timestamp', db_index=True)

    open = models.DecimalField('Open', max_digits=15, decimal_places=4)
    high = models.DecimalField('High', max_digits=15, decimal_places=4)
    low = models.DecimalField('Low', max_digits=15, decimal_places=4)
    close = models.DecimalField('Close', max_digits=15, decimal_places=4)
    volume = models.BigIntegerField('Volume')

    # Metadata
    source = models.CharField('Data Source', max_length=50, default='')
    created_at = models.DateTimeField('Created At', auto_now_add=True)

    class Meta:
        db_table = 'market_quotes'
        verbose_name = 'Quote'
        verbose_name_plural = 'Quotes'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['symbol', '-timestamp']),
            models.Index(fields=['timestamp']),
        ]
        unique_together = [['symbol', 'timestamp', 'source']]

    def __str__(self):
        return f'{self.symbol} @ {self.timestamp}: ${self.close}'


class Indicator(models.Model):
    """Calculated technical indicators."""

    INDICATOR_TYPE_CHOICES = [
        ('rsi', 'RSI'),
        ('macd', 'MACD'),
        ('sma', 'Simple Moving Average'),
        ('ema', 'Exponential Moving Average'),
        ('bollinger', 'Bollinger Bands'),
        ('atr', 'Average True Range'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField('Symbol', max_length=20, db_index=True)
    indicator_type = models.CharField('Indicator Type', max_length=50, choices=INDICATOR_TYPE_CHOICES)
    timestamp = models.DateTimeField('Timestamp', db_index=True)

    value = models.DecimalField('Value', max_digits=15, decimal_places=4)
    parameters = models.JSONField('Parameters', default=dict)

    created_at = models.DateTimeField('Created At', auto_now_add=True)

    class Meta:
        db_table = 'market_indicators'
        verbose_name = 'Indicator'
        verbose_name_plural = 'Indicators'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['symbol', 'indicator_type', '-timestamp']),
        ]

    def __str__(self):
        return f'{self.symbol} - {self.indicator_type}: {self.value}'
