"""
Orders admin configuration.
"""
from django.contrib import admin
from django.utils.html import format_html
from apps.orders.models import Order, Trade
from core.admin_2fa import secure_admin_site


@admin.register(Order, site=secure_admin_site)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'side', 'order_type', 'quantity', 'status_badge',
                    'requires_approval', 'created_at']
    list_filter = ['status', 'side', 'order_type', 'requires_approval', 'created_at']
    search_fields = ['symbol', 'broker_order_id', 'portfolio__user__email']
    readonly_fields = ['filled_qty', 'filled_avg_price', 'created_at', 'updated_at',
                       'submitted_at', 'filled_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Order Details', {'fields': ('portfolio', 'strategy', 'symbol', 'order_type', 'side')}),
        ('Quantity & Pricing', {'fields': ('quantity', 'limit_price', 'stop_price',
                                            'filled_qty', 'filled_avg_price')}),
        ('Status', {'fields': ('status', 'broker_order_id', 'error_message')}),
        ('Approval (HITL)', {'fields': ('requires_approval', 'approval_requested_at',
                                        'approved_by', 'approved_at', 'rejection_reason')}),
        ('Agent Decision', {'fields': ('agent_decision_id', 'agent_rationale', 'agent_confidence')}),
        ('Metadata', {'fields': ('created_at', 'updated_at', 'submitted_at', 'filled_at'),
                      'classes': ('collapse',)}),
    )

    def status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'pending_approval': '#ffc107',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'filled': '#28a745',
            'cancelled': '#6c757d',
            'failed': '#dc3545'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#6c757d'), obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(Trade, site=secure_admin_site)
class TradeAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'side', 'trade_type', 'quantity', 'price',
                    'realized_pnl_display', 'executed_at']
    list_filter = ['side', 'trade_type', 'executed_at']
    search_fields = ['symbol', 'broker_trade_id']
    readonly_fields = ['created_at']
    date_hierarchy = 'executed_at'

    def realized_pnl_display(self, obj):
        if obj.realized_pnl is None:
            return '-'
        color = 'green' if obj.realized_pnl >= 0 else 'red'
        return format_html(
            '<span style="color: {};">${:,.2f} ({:.2f}%)</span>',
            color, obj.realized_pnl, obj.realized_pnl_pct or 0
        )
    realized_pnl_display.short_description = 'Realized P&L'
