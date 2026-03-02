"""
Market Data admin configuration with custom actions for manual data sync.
"""
from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.http import JsonResponse
from datetime import datetime, timedelta, date
import logging

from .models import Quote, Indicator
from .tasks import (
    sync_latest_quotes,
    sync_historical_bars,
    calculate_indicators_for_symbol,
    backfill_historical_data,
    cleanup_old_quotes
)
from .cache import MarketDataCache
from .provider_manager import get_provider_manager

logger = logging.getLogger(__name__)


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    """Admin interface for Quote model with manual sync actions."""

    list_display = [
        'symbol',
        'timestamp',
        'close_formatted',
        'volume_formatted',
        'source',
        'created_at'
    ]
    list_filter = ['source', 'timestamp']
    search_fields = ['symbol']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'
    actions = [
        'sync_selected_symbols',
        'invalidate_cache_for_symbols',
        'calculate_indicators_for_symbols'
    ]

    def close_formatted(self, obj):
        """Format close price with color."""
        return format_html(
            '<span style="font-weight: bold;">${}</span>',
            obj.close
        )
    close_formatted.short_description = 'Close Price'

    def volume_formatted(self, obj):
        """Format volume with thousands separator."""
        return f"{obj.volume:,}"
    volume_formatted.short_description = 'Volume'

    def sync_selected_symbols(self, request, queryset):
        """Sync latest quotes for selected symbols."""
        symbols = list(queryset.values_list('symbol', flat=True).distinct())

        if symbols:
            # Queue Celery task
            task = sync_latest_quotes.delay(symbols, use_cache=False)
            self.message_user(
                request,
                f"Queued sync task for {len(symbols)} symbols: {', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}",
                messages.SUCCESS
            )
        else:
            self.message_user(request, "No symbols selected", messages.WARNING)

    sync_selected_symbols.short_description = "🔄 Sync latest quotes for selected symbols"

    def invalidate_cache_for_symbols(self, request, queryset):
        """Invalidate cache for selected symbols."""
        symbols = list(queryset.values_list('symbol', flat=True).distinct())
        invalidated = 0

        for symbol in symbols:
            MarketDataCache.invalidate_symbol(symbol)
            invalidated += 1

        self.message_user(
            request,
            f"Invalidated cache for {invalidated} symbols",
            messages.SUCCESS
        )

    invalidate_cache_for_symbols.short_description = "🗑️ Clear cache for selected symbols"

    def calculate_indicators_for_symbols(self, request, queryset):
        """Calculate indicators for selected symbols."""
        symbols = list(queryset.values_list('symbol', flat=True).distinct())

        for symbol in symbols:
            calculate_indicators_for_symbol.delay(symbol)

        self.message_user(
            request,
            f"Queued indicator calculation for {len(symbols)} symbols",
            messages.SUCCESS
        )

    calculate_indicators_for_symbols.short_description = "📊 Calculate indicators for selected"

    def get_urls(self):
        """Add custom admin URLs."""
        urls = super().get_urls()
        custom_urls = [
            path('sync-dashboard/', self.admin_site.admin_view(self.sync_dashboard_view), name='market_data_sync_dashboard'),
            path('sync-symbol/', self.admin_site.admin_view(self.sync_symbol_view), name='market_data_sync_symbol'),
            path('provider-status/', self.admin_site.admin_view(self.provider_status_view), name='market_data_provider_status'),
        ]
        return custom_urls + urls

    def sync_dashboard_view(self, request):
        """Custom dashboard view for market data management."""
        context = {
            **self.admin_site.each_context(request),
            'title': 'Market Data Sync Dashboard',
            'total_quotes': Quote.objects.count(),
            'total_indicators': Indicator.objects.count(),
            'unique_symbols': Quote.objects.values('symbol').distinct().count(),
            'cache_stats': MarketDataCache.get_cache_stats(),
            'provider_status': get_provider_manager().get_provider_status(),
        }

        return render(request, 'admin/market_data/sync_dashboard.html', context)

    def sync_symbol_view(self, request):
        """View to manually sync a symbol."""
        if request.method == 'POST':
            symbol = request.POST.get('symbol', '').upper()
            action = request.POST.get('action')

            if not symbol:
                messages.error(request, "Symbol is required")
                return redirect('admin:market_data_sync_dashboard')

            try:
                if action == 'sync_latest':
                    sync_latest_quotes.delay([symbol], use_cache=False)
                    messages.success(request, f"Queued latest quote sync for {symbol}")

                elif action == 'backfill':
                    days = int(request.POST.get('days', 365))
                    backfill_historical_data.delay(symbol, days=days)
                    messages.success(request, f"Queued {days}-day backfill for {symbol}")

                elif action == 'calculate_indicators':
                    calculate_indicators_for_symbol.delay(symbol)
                    messages.success(request, f"Queued indicator calculation for {symbol}")

                elif action == 'invalidate_cache':
                    MarketDataCache.invalidate_symbol(symbol)
                    messages.success(request, f"Invalidated cache for {symbol}")

                else:
                    messages.error(request, "Invalid action")

            except Exception as e:
                logger.error(f"Error in sync_symbol_view: {e}")
                messages.error(request, f"Error: {str(e)}")

            return redirect('admin:market_data_sync_dashboard')

        return redirect('admin:market_data_sync_dashboard')

    def provider_status_view(self, request):
        """API endpoint to get provider status."""
        manager = get_provider_manager()
        status = manager.get_provider_status()

        return JsonResponse({
            'status': 'ok',
            'providers': status,
            'cache_stats': MarketDataCache.get_cache_stats()
        })


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    """Admin interface for Indicator model."""

    list_display = [
        'symbol',
        'indicator_type',
        'value_formatted',
        'timestamp',
        'parameters_display'
    ]
    list_filter = ['indicator_type', 'symbol', 'timestamp']
    search_fields = ['symbol']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'

    def value_formatted(self, obj):
        """Format indicator value."""
        return f"{obj.value:.4f}"
    value_formatted.short_description = 'Value'

    def parameters_display(self, obj):
        """Display parameters as formatted string."""
        if obj.parameters:
            return ', '.join([f"{k}={v}" for k, v in obj.parameters.items()])
        return '-'
    parameters_display.short_description = 'Parameters'


# Custom admin site configuration
class MarketDataAdminSite(admin.AdminSite):
    """Custom admin site with market data dashboard."""
    site_header = "ShefaAI Market Data Admin"
    site_title = "Market Data Admin"
    index_title = "Market Data Management"
