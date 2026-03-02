"""
Strategy admin configuration.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Strategy, Backtest


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ['name', 'user_email', 'strategy_type', 'status_badge',
                    'win_rate', 'total_pnl_display', 'created_at']
    list_filter = ['strategy_type', 'status', 'created_at']
    search_fields = ['name', 'user__email']
    readonly_fields = ['total_trades', 'winning_trades', 'win_rate', 'total_pnl',
                       'sharpe_ratio', 'created_at', 'updated_at', 'activated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Info', {'fields': ('user', 'portfolio', 'name', 'description', 'strategy_type', 'status')}),
        ('Configuration', {'fields': ('config', 'watchlist')}),
        ('Risk Parameters', {'fields': ('position_size_pct', 'max_positions', 'max_daily_loss_pct')}),
        ('Entry/Exit Rules', {'fields': ('entry_rules', 'exit_rules')}),
        ('Performance', {'fields': ('total_trades', 'winning_trades', 'win_rate', 'total_pnl', 'sharpe_ratio')}),
        ('Metadata', {'fields': ('created_at', 'updated_at', 'activated_at'), 'classes': ('collapse',)}),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def status_badge(self, obj):
        colors = {
            'active': '#28a745',
            'paused': '#ffc107',
            'inactive': '#6c757d',
            'testing': '#17a2b8'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, '#6c757d'), obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def total_pnl_display(self, obj):
        color = 'green' if obj.total_pnl >= 0 else 'red'
        return format_html('<span style="color: {};">${:,.2f}</span>', color, obj.total_pnl)
    total_pnl_display.short_description = 'Total P&L'


@admin.register(Backtest)
class BacktestAdmin(admin.ModelAdmin):
    list_display = ['strategy_name', 'start_date', 'end_date', 'status_badge',
                    'total_return', 'sharpe_ratio', 'win_rate', 'created_at']
    list_filter = ['status', 'start_date', 'created_at']
    search_fields = ['strategy__name']
    readonly_fields = ['created_at', 'completed_at']
    date_hierarchy = 'created_at'

    def strategy_name(self, obj):
        return obj.strategy.name
    strategy_name.short_description = 'Strategy'

    def status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'running': '#17a2b8',
            'completed': '#28a745',
            'failed': '#dc3545'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, '#6c757d'), obj.get_status_display()
        )
    status_badge.short_description = 'Status'
