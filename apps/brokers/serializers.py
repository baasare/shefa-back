"""
Broker serializers for ShefaAI Trading Platform.
"""
from rest_framework import serializers
from .models import BrokerConnection


class BrokerConnectionSerializer(serializers.ModelSerializer):
    """Serializer for BrokerConnection model."""
    
    user_email = serializers.EmailField(source='user.email', read_only=True)
    portfolio_name = serializers.CharField(source='portfolio.name', read_only=True, allow_null=True)
    is_connected = serializers.SerializerMethodField()
    
    # Write-only fields for API credentials
    api_key = serializers.CharField(write_only=True, required=False)
    api_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = BrokerConnection
        fields = [
            'id', 'user', 'user_email', 'portfolio', 'portfolio_name',
            'broker', 'status', 'is_connected', 'account_number',
            'is_paper_trading', 'last_sync_at', 'last_error',
            'api_key', 'api_secret', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'status', 'last_sync_at', 'last_error',
            'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'api_key_encrypted': {'write_only': True},
            'api_secret_encrypted': {'write_only': True}
        }
    
    def get_is_connected(self, obj):
        """Check if connection is active."""
        return obj.status == 'active'
    
    def create(self, validated_data):
        """Create broker connection with encrypted credentials."""
        api_key = validated_data.pop('api_key', None)
        api_secret = validated_data.pop('api_secret', '')
        
        # TODO: Implement proper encryption
        # For now, just store as-is (NOT PRODUCTION READY!)
        validated_data['api_key_encrypted'] = api_key or ''
        validated_data['api_secret_encrypted'] = api_secret
        validated_data['user'] = self.context['request'].user
        validated_data['status'] = 'inactive'
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update broker connection."""
        api_key = validated_data.pop('api_key', None)
        api_secret = validated_data.pop('api_secret', None)
        
        # Update credentials if provided
        if api_key:
            instance.api_key_encrypted = api_key  # TODO: Encrypt
        if api_secret:
            instance.api_secret_encrypted = api_secret  # TODO: Encrypt
        
        return super().update(instance, validated_data)
