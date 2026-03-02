"""
Market Data serializers for ShefaAI Trading Platform.
"""
from rest_framework import serializers
from .models import Quote, Indicator


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
