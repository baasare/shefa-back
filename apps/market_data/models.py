"""
Market Data models for ShefaFx Trading Platform.
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


class StockScreener(models.Model):
    """Stock data for screening and filtering."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.CharField('Symbol', max_length=20, unique=True, db_index=True)
    name = models.CharField('Company Name', max_length=255)

    # Price Data
    price = models.DecimalField('Current Price', max_digits=15, decimal_places=4)
    change_pct = models.DecimalField('Change %', max_digits=10, decimal_places=4, null=True, blank=True)
    volume = models.BigIntegerField('Volume', null=True, blank=True)
    avg_volume = models.BigIntegerField('Avg Volume (30d)', null=True, blank=True)

    # Market Metrics
    market_cap = models.BigIntegerField('Market Cap', null=True, blank=True)
    pe_ratio = models.DecimalField('P/E Ratio', max_digits=15, decimal_places=4, null=True, blank=True)
    dividend_yield = models.DecimalField('Dividend Yield %', max_digits=10, decimal_places=4, null=True, blank=True)

    # Technical Indicators
    rsi = models.DecimalField('RSI', max_digits=10, decimal_places=4, null=True, blank=True)
    sma_50 = models.DecimalField('SMA 50', max_digits=15, decimal_places=4, null=True, blank=True)
    sma_200 = models.DecimalField('SMA 200', max_digits=15, decimal_places=4, null=True, blank=True)

    # Price Ranges
    week_52_high = models.DecimalField('52 Week High', max_digits=15, decimal_places=4, null=True, blank=True)
    week_52_low = models.DecimalField('52 Week Low', max_digits=15, decimal_places=4, null=True, blank=True)

    # Classification
    sector = models.CharField('Sector', max_length=100, blank=True)
    industry = models.CharField('Industry', max_length=100, blank=True)
    exchange = models.CharField('Exchange', max_length=50, default='')

    # Metadata
    last_updated = models.DateTimeField('Last Updated', auto_now=True)
    created_at = models.DateTimeField('Created At', auto_now_add=True)

    class Meta:
        db_table = 'stock_screener'
        verbose_name = 'Stock Screener Data'
        verbose_name_plural = 'Stock Screener Data'
        ordering = ['symbol']
        indexes = [
            models.Index(fields=['symbol']),
            models.Index(fields=['sector']),
            models.Index(fields=['industry']),
            models.Index(fields=['market_cap']),
            models.Index(fields=['volume']),
            models.Index(fields=['rsi']),
        ]

    def __str__(self):
        return f'{self.symbol} - {self.name}'
