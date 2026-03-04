"""
Portfolio admin configuration.
"""
from django.contrib import admin
from django.utils.html import format_html
from apps.portfolios.models import Portfolio, Position, PortfolioSnapshot
from core.admin_2fa import secure_admin_site


@admin.register(Portfolio, site=secure_admin_site)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ['name', 'user_email', 'portfolio_type', 'total_equity_display',
                    'total_pnl_display', 'win_rate', 'is_active', 'created_at']
    list_filter = ['portfolio_type', 'is_active', 'created_at']
    search_fields = ['name', 'user__email']
    readonly_fields = ['total_equity', 'total_pnl', 'total_pnl_pct', 'win_rate',
                       'created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Info', {'fields': ('user', 'name', 'portfolio_type', 'is_active')}),
        ('Balances', {'fields': ('initial_capital', 'cash_balance', 'total_equity')}),
        ('P&L', {'fields': ('daily_pnl', 'total_pnl', 'total_pnl_pct')}),
        ('Performance', {'fields': ('total_trades', 'winning_trades', 'losing_trades', 'win_rate')}),
        ('Risk Metrics', {'fields': ('max_drawdown', 'sharpe_ratio')}),
        ('Metadata', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def user_email(self, obj):
        return obj.user.email

    user_email.short_description = 'User'

    def total_equity_display(self, obj):
        return f'${obj.total_equity:,.2f}'

    total_equity_display.short_description = 'Total Equity'

    def total_pnl_display(self, obj):
        color = 'green' if obj.total_pnl >= 0 else 'red'
        return format_html(
            '<span style="color: {};">{}</span>',
            color, f'${obj.total_pnl:,.2f} ({obj.total_pnl_pct:.2f}%)'
        )

    total_pnl_display.short_description = 'Total P&L'


@admin.register(Position, site=secure_admin_site)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'portfolio_name', 'side', 'quantity', 'avg_entry_price',
                    'current_price', 'unrealized_pnl_display', 'opened_at']
    list_filter = ['side', 'opened_at']
    search_fields = ['symbol', 'portfolio__name', 'portfolio__user__email']
    readonly_fields = ['cost_basis', 'current_value', 'unrealized_pnl',
                       'unrealized_pnl_pct', 'opened_at', 'updated_at']
    date_hierarchy = 'opened_at'

    def portfolio_name(self, obj):
        return obj.portfolio.name

    portfolio_name.short_description = 'Portfolio'

    def unrealized_pnl_display(self, obj):
        color = 'green' if obj.unrealized_pnl >= 0 else 'red'
        return format_html(
            '<span style="color: {};">{}</span>',
            color, f'${obj.unrealized_pnl:,.2f} ({obj.unrealized_pnl_pct:.2f}%)'
        )

    unrealized_pnl_display.short_description = 'Unrealized P&L'


@admin.register(PortfolioSnapshot, site=secure_admin_site)
class PortfolioSnapshotAdmin(admin.ModelAdmin):
    list_display = ['portfolio_name', 'snapshot_date', 'total_equity', 'daily_pnl', 'win_rate']
    list_filter = ['snapshot_date']
    search_fields = ['portfolio__name']
    readonly_fields = ['created_at']
    date_hierarchy = 'snapshot_date'

    def portfolio_name(self, obj):
        return obj.portfolio.name

    portfolio_name.short_description = 'Portfolio'
