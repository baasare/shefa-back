"""
Portfolio serializers for ShefaAI Trading Platform.
"""
from rest_framework import serializers
from .models import Portfolio, Position, PortfolioSnapshot
from decimal import Decimal


class PortfolioSnapshotSerializer(serializers.ModelSerializer):
    """Serializer for PortfolioSnapshot model."""
    
    class Meta:
        model = PortfolioSnapshot
        fields = [
            'id', 'portfolio', 'snapshot_date', 'total_equity', 
            'cash_balance', 'positions_value', 'daily_pnl', 
            'cumulative_pnl', 'total_trades', 'win_rate', 
            'sharpe_ratio', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class PositionSerializer(serializers.ModelSerializer):
    """Serializer for Position model."""
    
    symbol = serializers.CharField(max_length=20)
    unrealized_pnl_display = serializers.SerializerMethodField()
    portfolio_name = serializers.CharField(source='portfolio.name', read_only=True)
    
    class Meta:
        model = Position
        fields = [
            'id', 'portfolio', 'portfolio_name', 'strategy', 'symbol', 'side',
            'quantity', 'avg_entry_price', 'current_price', 'cost_basis',
            'current_value', 'unrealized_pnl', 'unrealized_pnl_pct',
            'unrealized_pnl_display', 'stop_loss_price', 'take_profit_price',
            'trailing_stop_enabled', 'trailing_stop_pct',
            'opened_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'current_value', 'unrealized_pnl', 
            'unrealized_pnl_pct', 'opened_at', 'updated_at'
        ]
    
    def get_unrealized_pnl_display(self, obj):
        """Format unrealized P&L for display."""
        return {
            'amount': float(obj.unrealized_pnl),
            'percentage': float(obj.unrealized_pnl_pct),
            'is_profit': obj.unrealized_pnl >= 0
        }
    
    def validate_quantity(self, value):
        """Validate quantity is positive."""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value
    
    def validate(self, data):
        """Validate position data."""
        if data.get('stop_loss_price') and data.get('avg_entry_price'):
            if data['side'] == 'long' and data['stop_loss_price'] >= data['avg_entry_price']:
                raise serializers.ValidationError(
                    "Stop loss for long position must be below entry price"
                )
            elif data['side'] == 'short' and data['stop_loss_price'] <= data['avg_entry_price']:
                raise serializers.ValidationError(
                    "Stop loss for short position must be above entry price"
                )
        return data


class PositionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for position lists."""
    
    unrealized_pnl_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Position
        fields = [
            'id', 'symbol', 'side', 'quantity', 'avg_entry_price',
            'current_price', 'unrealized_pnl', 'unrealized_pnl_pct',
            'unrealized_pnl_display', 'opened_at'
        ]
    
    def get_unrealized_pnl_display(self, obj):
        return {
            'amount': float(obj.unrealized_pnl),
            'percentage': float(obj.unrealized_pnl_pct),
            'is_profit': obj.unrealized_pnl >= 0
        }


class PortfolioSerializer(serializers.ModelSerializer):
    """Serializer for Portfolio model."""
    
    positions = PositionListSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    total_pnl_display = serializers.SerializerMethodField()
    performance_summary = serializers.SerializerMethodField()
    
    class Meta:
        model = Portfolio
        fields = [
            'id', 'user', 'user_email', 'name', 'portfolio_type',
            'initial_capital', 'cash_balance', 'total_equity',
            'daily_pnl', 'total_pnl', 'total_pnl_pct', 'total_pnl_display',
            'total_trades', 'winning_trades', 'losing_trades', 'win_rate',
            'max_drawdown', 'sharpe_ratio', 'is_active',
            'performance_summary', 'positions',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'total_equity', 'daily_pnl', 'total_pnl',
            'total_pnl_pct', 'total_trades', 'winning_trades',
            'losing_trades', 'win_rate', 'max_drawdown', 'sharpe_ratio',
            'created_at', 'updated_at'
        ]
    
    def get_total_pnl_display(self, obj):
        """Format total P&L for display."""
        return {
            'amount': float(obj.total_pnl),
            'percentage': float(obj.total_pnl_pct),
            'is_profit': obj.total_pnl >= 0
        }
    
    def get_performance_summary(self, obj):
        """Get portfolio performance summary."""
        return {
            'total_equity': float(obj.total_equity),
            'cash_balance': float(obj.cash_balance),
            'positions_value': float(obj.total_equity - obj.cash_balance),
            'total_pnl': float(obj.total_pnl),
            'total_pnl_pct': float(obj.total_pnl_pct),
            'win_rate': float(obj.win_rate),
            'total_trades': obj.total_trades,
            'open_positions': obj.positions.count()
        }
    
    def validate_initial_capital(self, value):
        """Validate initial capital is positive."""
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Initial capital must be greater than 0")
        return value
    
    def validate_name(self, value):
        """Validate portfolio name is unique for user."""
        user = self.context['request'].user
        if self.instance:
            # Updating existing portfolio
            if Portfolio.objects.filter(user=user, name=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("You already have a portfolio with this name")
        else:
            # Creating new portfolio
            if Portfolio.objects.filter(user=user, name=value).exists():
                raise serializers.ValidationError("You already have a portfolio with this name")
        return value
    
    def create(self, validated_data):
        """Create portfolio with user from request."""
        validated_data['user'] = self.context['request'].user
        # Set cash balance to initial capital on creation
        validated_data['cash_balance'] = validated_data['initial_capital']
        validated_data['total_equity'] = validated_data['initial_capital']
        return super().create(validated_data)


class PortfolioListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for portfolio lists."""
    
    total_pnl_display = serializers.SerializerMethodField()
    open_positions_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Portfolio
        fields = [
            'id', 'name', 'portfolio_type', 'total_equity',
            'total_pnl', 'total_pnl_pct', 'total_pnl_display',
            'win_rate', 'is_active', 'open_positions_count', 'created_at'
        ]
    
    def get_total_pnl_display(self, obj):
        return {
            'amount': float(obj.total_pnl),
            'percentage': float(obj.total_pnl_pct),
            'is_profit': obj.total_pnl >= 0
        }
    
    def get_open_positions_count(self, obj):
        return obj.positions.count()
