"""
Market Data serializers for ShefaFx Trading Platform.
"""
from rest_framework import serializers
from apps.market_data.models import Quote, Indicator, StockScreener, Watchlist


class QuoteSerializer(serializers.ModelSerializer):
    """Serializer for Quote model."""
    
    class Meta:
        model = Quote
        fields = [
            'id', 'symbol', 'timestamp', 'open', 'high', 'low', 'close',
            'volume', 'source', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate_symbol(self, value):
        """Validate and normalize symbol."""
        return value.upper().strip()


class IndicatorSerializer(serializers.ModelSerializer):
    """Serializer for Indicator model."""

    class Meta:
        model = Indicator
        fields = [
            'id', 'symbol', 'indicator_type', 'timestamp',
            'value', 'parameters', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate_symbol(self, value):
        """Validate and normalize symbol."""
        return value.upper().strip()


class StockScreenerSerializer(serializers.ModelSerializer):
    """Serializer for Stock Screener model."""

    price_vs_52w_high_pct = serializers.SerializerMethodField()
    price_vs_52w_low_pct = serializers.SerializerMethodField()
    above_sma_50 = serializers.SerializerMethodField()
    above_sma_200 = serializers.SerializerMethodField()
    signal = serializers.SerializerMethodField()

    class Meta:
        model = StockScreener
        fields = [
            'id', 'symbol', 'name', 'price', 'change_pct', 'volume', 'avg_volume',
            'market_cap', 'pe_ratio', 'dividend_yield', 'rsi', 'sma_50', 'sma_200',
            'week_52_high', 'week_52_low', 'price_vs_52w_high_pct', 'price_vs_52w_low_pct',
            'above_sma_50', 'above_sma_200', 'sector', 'industry', 'exchange',
            'signal', 'last_updated', 'created_at'
        ]
        read_only_fields = ['id', 'last_updated', 'created_at']

    def get_price_vs_52w_high_pct(self, obj):
        """Calculate percentage from 52-week high."""
        if obj.price and obj.week_52_high:
            return float(((obj.price - obj.week_52_high) / obj.week_52_high) * 100)
        return None

    def get_price_vs_52w_low_pct(self, obj):
        """Calculate percentage from 52-week low."""
        if obj.price and obj.week_52_low:
            return float(((obj.price - obj.week_52_low) / obj.week_52_low) * 100)
        return None

    def get_above_sma_50(self, obj):
        """Check if price is above SMA 50."""
        if obj.price and obj.sma_50:
            return obj.price > obj.sma_50
        return None

    def get_above_sma_200(self, obj):
        """Check if price is above SMA 200."""
        if obj.price and obj.sma_200:
            return obj.price > obj.sma_200
        return None

    def get_signal(self, obj):
        """Derive a trading signal from RSI."""
        if obj.rsi is None:
            return 'Neutral'
        rsi = float(obj.rsi)
        if rsi >= 70:
            return 'Sell'
        elif rsi >= 50:
            return 'Buy'
        elif rsi >= 30:
            return 'Hold'
        return 'Neutral'

    def validate_symbol(self, value):
        """Validate and normalize symbol."""
        return value.upper().strip()


class StockScreenerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for stock screener lists."""

    signal = serializers.SerializerMethodField()

    class Meta:
        model = StockScreener
        fields = [
            'id', 'symbol', 'name', 'price', 'change_pct', 'volume',
            'market_cap', 'sector', 'rsi', 'pe_ratio', 'signal'
        ]

    def get_signal(self, obj):
        """Derive a trading signal from RSI."""
        if obj.rsi is None:
            return 'Neutral'
        rsi = float(obj.rsi)
        if rsi >= 70:
            return 'Sell'
        elif rsi >= 50:
            return 'Buy'
        elif rsi >= 30:
            return 'Hold'
        return 'Neutral'


class WatchlistSerializer(serializers.ModelSerializer):
    """Serializer for user's watchlist items."""

    class Meta:
        model = Watchlist
        fields = ['id', 'symbol', 'name', 'asset_type', 'added_at']
        read_only_fields = ['id', 'added_at']

    def validate_symbol(self, value):
        return value.upper().strip()

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)
