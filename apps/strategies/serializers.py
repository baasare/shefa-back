"""
Strategy serializers for ShefaFx Trading Platform.
"""
from rest_framework import serializers
from apps.strategies.models import Strategy, Backtest


class BacktestSerializer(serializers.ModelSerializer):
    """Serializer for Backtest model."""
    
    strategy_name = serializers.CharField(source='strategy.name', read_only=True)
    performance_summary = serializers.SerializerMethodField()
    duration_days = serializers.SerializerMethodField()
    
    class Meta:
        model = Backtest
        fields = [
            'id', 'strategy', 'strategy_name', 'start_date', 'end_date',
            'duration_days', 'initial_capital', 'final_capital',
            'total_return', 'annual_return', 'sharpe_ratio', 'sortino_ratio',
            'max_drawdown', 'total_trades', 'winning_trades', 'losing_trades',
            'win_rate', 'avg_trade_pnl', 'results', 'equity_curve',
            'status', 'error_message', 'performance_summary',
            'created_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'final_capital', 'total_return', 'annual_return',
            'sharpe_ratio', 'sortino_ratio', 'max_drawdown',
            'winning_trades', 'losing_trades', 'win_rate',
            'avg_trade_pnl', 'status', 'created_at', 'completed_at'
        ]
    
    def get_duration_days(self, obj):
        """Calculate backtest duration in days."""
        if obj.start_date and obj.end_date:
            return (obj.end_date - obj.start_date).days
        return None
    
    def get_performance_summary(self, obj):
        """Get backtest performance summary."""
        if obj.status != 'completed':
            return None
        
        return {
            'total_return': float(obj.total_return) if obj.total_return else None,
            'annual_return': float(obj.annual_return) if obj.annual_return else None,
            'sharpe_ratio': float(obj.sharpe_ratio) if obj.sharpe_ratio else None,
            'max_drawdown': float(obj.max_drawdown) if obj.max_drawdown else None,
            'win_rate': float(obj.win_rate),
            'total_trades': obj.total_trades,
            'profit_factor': self._calculate_profit_factor(obj)
        }
    
    def _calculate_profit_factor(self, obj):
        """Calculate profit factor (gross profit / gross loss)."""
        # Placeholder - would calculate from results data
        return None
    
    def validate(self, data):
        """Validate backtest data."""
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] >= data['end_date']:
                raise serializers.ValidationError("End date must be after start date")
        return data


class StrategySerializer(serializers.ModelSerializer):
    """Serializer for Strategy model."""
    
    user_email = serializers.EmailField(source='user.email', read_only=True)
    portfolio_name = serializers.CharField(source='portfolio.name', read_only=True, allow_null=True)
    backtests = BacktestSerializer(many=True, read_only=True)
    performance_summary = serializers.SerializerMethodField()
    watchlist_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Strategy
        fields = [
            'id', 'user', 'user_email', 'portfolio', 'portfolio_name',
            'name', 'description', 'strategy_type', 'status',
            'config', 'watchlist', 'watchlist_count',
            'position_size_pct', 'max_positions', 'max_daily_loss_pct',
            'entry_rules', 'exit_rules',
            'total_trades', 'winning_trades', 'win_rate', 'total_pnl',
            'sharpe_ratio', 'performance_summary', 'backtests',
            'created_at', 'updated_at', 'activated_at'
        ]
        read_only_fields = [
            'id', 'user', 'total_trades', 'winning_trades', 'win_rate',
            'total_pnl', 'sharpe_ratio', 'created_at', 'updated_at', 'activated_at'
        ]
    
    def get_watchlist_count(self, obj):
        """Get count of symbols in watchlist."""
        return len(obj.watchlist) if obj.watchlist else 0
    
    def get_performance_summary(self, obj):
        """Get strategy performance summary."""
        return {
            'total_trades': obj.total_trades,
            'winning_trades': obj.winning_trades,
            'win_rate': float(obj.win_rate),
            'total_pnl': float(obj.total_pnl),
            'sharpe_ratio': float(obj.sharpe_ratio) if obj.sharpe_ratio else None,
            'is_active': obj.status == 'active'
        }
    
    def validate_watchlist(self, value):
        """Validate watchlist contains valid symbols."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Watchlist must be a list")
        
        # Convert to uppercase and remove duplicates
        value = list(set([str(symbol).upper().strip() for symbol in value]))
        
        # Validate each symbol (basic validation)
        for symbol in value:
            if not symbol or len(symbol) > 10:
                raise serializers.ValidationError(f"Invalid symbol: {symbol}")
        
        return value
    
    def validate(self, data):
        """Validate strategy data."""
        # Validate position size
        if data.get('position_size_pct') and data['position_size_pct'] <= 0:
            raise serializers.ValidationError("Position size must be greater than 0")
        
        # Validate max positions
        if data.get('max_positions') and data['max_positions'] <= 0:
            raise serializers.ValidationError("Max positions must be greater than 0")
        
        return data
    
    def create(self, validated_data):
        """Create strategy with user from request."""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class StrategyListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for strategy lists."""
    
    watchlist_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Strategy
        fields = [
            'id', 'name', 'strategy_type', 'status',
            'watchlist_count', 'win_rate', 'total_pnl',
            'created_at', 'activated_at'
        ]
    
    def get_watchlist_count(self, obj):
        return len(obj.watchlist) if obj.watchlist else 0
