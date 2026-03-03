"""
Order serializers for ShefaFx Trading Platform.
"""
from rest_framework import serializers
from .models import Order, Trade
from django.utils import timezone


class TradeSerializer(serializers.ModelSerializer):
    """Serializer for Trade model."""
    
    portfolio_name = serializers.CharField(source='portfolio.name', read_only=True)
    strategy_name = serializers.CharField(source='strategy.name', read_only=True, allow_null=True)
    pnl_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Trade
        fields = [
            'id', 'portfolio', 'portfolio_name', 'position', 'order',
            'strategy', 'strategy_name', 'symbol', 'trade_type', 'side',
            'quantity', 'price', 'commission', 'total_value',
            'realized_pnl', 'realized_pnl_pct', 'pnl_display',
            'broker_trade_id', 'executed_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_pnl_display(self, obj):
        """Format P&L for display."""
        if obj.realized_pnl is None:
            return None
        
        return {
            'amount': float(obj.realized_pnl),
            'percentage': float(obj.realized_pnl_pct) if obj.realized_pnl_pct else None,
            'is_profit': obj.realized_pnl >= 0
        }


class OrderSerializer(serializers.ModelSerializer):
    """Serializer for Order model."""
    
    portfolio_name = serializers.CharField(source='portfolio.name', read_only=True)
    strategy_name = serializers.CharField(source='strategy.name', read_only=True, allow_null=True)
    approved_by_email = serializers.EmailField(source='approved_by.email', read_only=True, allow_null=True)
    trades = TradeSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_pending_approval = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'portfolio', 'portfolio_name', 'strategy', 'strategy_name',
            'symbol', 'order_type', 'side', 'quantity', 'limit_price', 'stop_price',
            'filled_qty', 'filled_avg_price', 'status', 'status_display',
            'broker_order_id', 'requires_approval', 'is_pending_approval',
            'approval_requested_at', 'approved_by', 'approved_by_email',
            'approved_at', 'rejection_reason', 'agent_decision_id',
            'agent_rationale', 'agent_confidence', 'error_message',
            'can_cancel', 'trades',
            'created_at', 'updated_at', 'submitted_at', 'filled_at'
        ]
        read_only_fields = [
            'id', 'filled_qty', 'filled_avg_price', 'status', 'broker_order_id',
            'approved_by', 'approved_at', 'error_message',
            'created_at', 'updated_at', 'submitted_at', 'filled_at'
        ]
    
    def get_is_pending_approval(self, obj):
        """Check if order is pending approval."""
        return obj.status == 'pending_approval'
    
    def get_can_cancel(self, obj):
        """Check if order can be cancelled."""
        return obj.status in ['pending', 'pending_approval', 'submitted']
    
    def validate_quantity(self, value):
        """Validate quantity is positive."""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value
    
    def validate_symbol(self, value):
        """Validate and normalize symbol."""
        return value.upper().strip()
    
    def validate(self, data):
        """Validate order data."""
        # Validate limit price for limit orders
        if data.get('order_type') == 'limit' and not data.get('limit_price'):
            raise serializers.ValidationError("Limit price is required for limit orders")
        
        # Validate stop price for stop orders
        if data.get('order_type') in ['stop', 'stop_limit'] and not data.get('stop_price'):
            raise serializers.ValidationError("Stop price is required for stop orders")
        
        # Check if order requires approval based on user settings
        if data.get('portfolio'):
            user = data['portfolio'].user
            # Calculate order value
            quantity = data.get('quantity', 0)
            price = data.get('limit_price') or data.get('stop_price') or 0
            order_value = quantity * price
            
            # Check against user's approval threshold
            if order_value > user.approval_threshold:
                data['requires_approval'] = True
                data['status'] = 'pending_approval'
                data['approval_requested_at'] = timezone.now()
        
        return data
    
    def create(self, validated_data):
        """Create order with initial status."""
        if 'status' not in validated_data:
            validated_data['status'] = 'pending'
        return super().create(validated_data)


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for order lists."""
    
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'symbol', 'side', 'order_type', 'quantity',
            'limit_price', 'stop_price', 'filled_qty', 'status',
            'status_display', 'requires_approval', 'created_at'
        ]


class OrderApprovalSerializer(serializers.Serializer):
    """Serializer for order approval/rejection."""
    
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        """Validate approval data."""
        if data['action'] == 'reject' and not data.get('rejection_reason'):
            raise serializers.ValidationError("Rejection reason is required when rejecting an order")
        return data
