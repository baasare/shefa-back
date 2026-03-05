"""
Market Data admin configuration with custom actions for manual data sync.
"""
import logging

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import path
from django.utils.html import format_html

from apps.market_data.cache import MarketDataCache
from apps.market_data.models import Indicator, Quote, StockScreener, Watchlist
from apps.market_data.provider_manager import get_provider_manager
from apps.market_data.tasks import (
    backfill_historical_data,
    calculate_indicators_for_symbol,
    cleanup_old_quotes,
    sync_latest_quotes,
)
from core.admin_2fa import secure_admin_site

logger = logging.getLogger(__name__)


def _distinct_symbols(queryset):
    """Return unique, uppercase symbols from a queryset."""
    return sorted(
        {
            (symbol or "").upper().strip()
            for symbol in queryset.values_list("symbol", flat=True)
            if symbol
        }
    )


@admin.register(Quote, site=secure_admin_site)
class QuoteAdmin(admin.ModelAdmin):
    """Admin interface for Quote model with manual sync actions."""

    list_display = [
        "symbol",
        "timestamp",
        "close_formatted",
        "volume_formatted",
        "source",
        "created_at",
    ]
    list_filter = ["source", "timestamp"]
    search_fields = ["symbol"]
    readonly_fields = ["created_at"]
    date_hierarchy = "timestamp"
    actions = [
        "sync_selected_symbols",
        "invalidate_cache_for_symbols",
        "calculate_indicators_for_symbols",
        "cleanup_old_quotes_action",
    ]

    def close_formatted(self, obj):
        """Format close price with color."""
        return format_html('<span style="font-weight: bold;">${}</span>', obj.close)

    close_formatted.short_description = "Close Price"

    def volume_formatted(self, obj):
        """Format volume with thousands separator."""
        return f"{obj.volume:,}"

    volume_formatted.short_description = "Volume"

    def sync_selected_symbols(self, request, queryset):
        """Sync latest quotes for selected symbols."""
        symbols = _distinct_symbols(queryset)

        if symbols:
            sync_latest_quotes.delay(symbols, use_cache=False)
            self.message_user(
                request,
                f"Queued sync task for {len(symbols)} symbols: "
                f"{', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}",
                messages.SUCCESS,
            )
        else:
            self.message_user(request, "No symbols selected", messages.WARNING)

    sync_selected_symbols.short_description = "🔄 Sync latest quotes for selected symbols"

    def invalidate_cache_for_symbols(self, request, queryset):
        """Invalidate cache for selected symbols."""
        symbols = _distinct_symbols(queryset)

        for symbol in symbols:
            MarketDataCache.invalidate_symbol(symbol)

        self.message_user(
            request,
            f"Invalidated cache for {len(symbols)} symbols",
            messages.SUCCESS,
        )

    invalidate_cache_for_symbols.short_description = "🗑️ Clear cache for selected symbols"

    def calculate_indicators_for_symbols(self, request, queryset):
        """Calculate indicators for selected symbols."""
        symbols = _distinct_symbols(queryset)

        for symbol in symbols:
            calculate_indicators_for_symbol.delay(symbol)

        self.message_user(
            request,
            f"Queued indicator calculation for {len(symbols)} symbols",
            messages.SUCCESS,
        )

    calculate_indicators_for_symbols.short_description = "📊 Calculate indicators for selected"

    def cleanup_old_quotes_action(self, request, queryset):
        """Cleanup old quotes older than specified days."""
        if "apply" in request.POST:
            days_to_keep = int(request.POST.get("days_to_keep", 365))
            task = cleanup_old_quotes.delay(days_to_keep=days_to_keep)

            self.message_user(
                request,
                f"Queued cleanup task to delete quotes older than {days_to_keep} days "
                f"(Task ID: {task.id})",
                messages.SUCCESS,
            )
            return None

        from django import forms

        class CleanupForm(forms.Form):
            days_to_keep = forms.IntegerField(
                initial=365,
                min_value=1,
                max_value=3650,
                label="Days to keep",
                help_text="Delete quotes older than this many days",
            )

        form = CleanupForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Cleanup Old Quotes",
            "queryset": queryset,
            "form": form,
            "action": "cleanup_old_quotes_action",
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        }

        return render(request, "admin/market_data/cleanup_old_quotes.html", context)

    cleanup_old_quotes_action.short_description = "🗑️ Cleanup old quotes (bulk)"

    def get_urls(self):
        """Add custom admin URLs."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "sync-dashboard/",
                self.admin_site.admin_view(self.sync_dashboard_view),
                name="market_data_sync_dashboard",
            ),
            path(
                "sync-symbol/",
                self.admin_site.admin_view(self.sync_symbol_view),
                name="market_data_sync_symbol",
            ),
            path(
                "provider-status/",
                self.admin_site.admin_view(self.provider_status_view),
                name="market_data_provider_status",
            ),
        ]
        return custom_urls + urls

    def sync_dashboard_view(self, request):
        """Custom dashboard view for market data management."""
        context = {
            **self.admin_site.each_context(request),
            "title": "Market Data Sync Dashboard",
            "total_quotes": Quote.objects.count(),
            "total_indicators": Indicator.objects.count(),
            "unique_symbols": Quote.objects.values("symbol").distinct().count(),
            "cache_stats": MarketDataCache.get_cache_stats(),
            "provider_status": get_provider_manager().get_provider_status(),
        }

        return render(request, "admin/market_data/sync_dashboard.html", context)

    def sync_symbol_view(self, request):
        """View to manually sync a symbol."""
        if request.method == "POST":
            symbol = request.POST.get("symbol", "").upper()
            action = request.POST.get("action")

            if not symbol:
                messages.error(request, "Symbol is required")
                return redirect("admin:market_data_sync_dashboard")

            try:
                if action == "sync_latest":
                    sync_latest_quotes.delay([symbol], use_cache=False)
                    messages.success(request, f"Queued latest quote sync for {symbol}")

                elif action == "backfill":
                    days = int(request.POST.get("days", 365))
                    backfill_historical_data.delay(symbol, days=days)
                    messages.success(request, f"Queued {days}-day backfill for {symbol}")

                elif action == "calculate_indicators":
                    calculate_indicators_for_symbol.delay(symbol)
                    messages.success(request, f"Queued indicator calculation for {symbol}")

                elif action == "invalidate_cache":
                    MarketDataCache.invalidate_symbol(symbol)
                    messages.success(request, f"Invalidated cache for {symbol}")

                else:
                    messages.error(request, "Invalid action")

            except Exception as e:
                logger.error(f"Error in sync_symbol_view: {e}")
                messages.error(request, f"Error: {str(e)}")

            return redirect("admin:market_data_sync_dashboard")

        return redirect("admin:market_data_sync_dashboard")

    def provider_status_view(self, request):
        """API endpoint to get provider status."""
        manager = get_provider_manager()
        status = manager.get_provider_status()

        return JsonResponse(
            {"status": "ok", "providers": status, "cache_stats": MarketDataCache.get_cache_stats()}
        )


@admin.register(Indicator, site=secure_admin_site)
class IndicatorAdmin(admin.ModelAdmin):
    """Admin interface for Indicator model."""

    list_display = [
        "symbol",
        "indicator_type",
        "value_formatted",
        "timestamp",
        "parameters_display",
    ]
    list_filter = ["indicator_type", "symbol", "timestamp"]
    search_fields = ["symbol"]
    readonly_fields = ["created_at"]
    date_hierarchy = "timestamp"
    actions = [
        "recalculate_for_selected_symbols",
        "clear_cache_for_selected_symbols",
    ]

    def value_formatted(self, obj):
        """Format indicator value."""
        return f"{obj.value:.4f}"

    value_formatted.short_description = "Value"

    def parameters_display(self, obj):
        """Display parameters as formatted string."""
        if obj.parameters:
            return ", ".join([f"{k}={v}" for k, v in obj.parameters.items()])
        return "-"

    parameters_display.short_description = "Parameters"

    def recalculate_for_selected_symbols(self, request, queryset):
        symbols = _distinct_symbols(queryset)
        for symbol in symbols:
            calculate_indicators_for_symbol.delay(symbol)

        self.message_user(
            request,
            f"Queued recalculation for {len(symbols)} symbols",
            messages.SUCCESS,
        )

    recalculate_for_selected_symbols.short_description = "📊 Recalculate indicators for selected symbols"

    def clear_cache_for_selected_symbols(self, request, queryset):
        symbols = _distinct_symbols(queryset)
        for symbol in symbols:
            MarketDataCache.invalidate_symbol(symbol)

        self.message_user(
            request,
            f"Cleared cache for {len(symbols)} symbols",
            messages.SUCCESS,
        )

    clear_cache_for_selected_symbols.short_description = "🗑️ Clear cache for selected symbols"


@admin.register(StockScreener, site=secure_admin_site)
class StockScreenerAdmin(admin.ModelAdmin):
    """Admin interface for StockScreener with sync-related actions."""

    list_display = [
        "symbol",
        "name",
        "price",
        "change_pct",
        "volume",
        "market_cap",
        "rsi",
        "sector",
        "exchange",
        "last_updated",
    ]
    list_filter = ["exchange", "sector", "industry", "last_updated"]
    search_fields = ["symbol", "name", "sector", "industry"]
    readonly_fields = ["created_at", "last_updated"]
    date_hierarchy = "last_updated"
    actions = [
        "sync_quotes_for_selected_symbols",
        "calculate_indicators_for_selected_symbols",
        "invalidate_cache_for_selected_symbols",
    ]

    def sync_quotes_for_selected_symbols(self, request, queryset):
        symbols = _distinct_symbols(queryset)
        if not symbols:
            self.message_user(request, "No symbols selected", messages.WARNING)
            return
        sync_latest_quotes.delay(symbols, use_cache=False)
        self.message_user(
            request,
            f"Queued quote sync for {len(symbols)} symbols",
            messages.SUCCESS,
        )

    sync_quotes_for_selected_symbols.short_description = "🔄 Sync latest quotes for selected symbols"

    def calculate_indicators_for_selected_symbols(self, request, queryset):
        symbols = _distinct_symbols(queryset)
        for symbol in symbols:
            calculate_indicators_for_symbol.delay(symbol)
        self.message_user(
            request,
            f"Queued indicator calculation for {len(symbols)} symbols",
            messages.SUCCESS,
        )

    calculate_indicators_for_selected_symbols.short_description = "📊 Calculate indicators for selected symbols"

    def invalidate_cache_for_selected_symbols(self, request, queryset):
        symbols = _distinct_symbols(queryset)
        for symbol in symbols:
            MarketDataCache.invalidate_symbol(symbol)
        self.message_user(
            request,
            f"Cleared cache for {len(symbols)} symbols",
            messages.SUCCESS,
        )

    invalidate_cache_for_selected_symbols.short_description = "🗑️ Clear cache for selected symbols"


@admin.register(Watchlist, site=secure_admin_site)
class WatchlistAdmin(admin.ModelAdmin):
    """Admin interface for Watchlist with symbol-level actions."""

    list_display = ["user", "symbol", "name", "asset_type", "added_at"]
    list_filter = ["asset_type", "added_at"]
    search_fields = ["symbol", "name", "user__email", "user__username"]
    readonly_fields = ["added_at"]
    date_hierarchy = "added_at"
    actions = [
        "sync_quotes_for_selected_symbols",
        "calculate_indicators_for_selected_symbols",
        "invalidate_cache_for_selected_symbols",
    ]

    def sync_quotes_for_selected_symbols(self, request, queryset):
        symbols = _distinct_symbols(queryset)
        if not symbols:
            self.message_user(request, "No symbols selected", messages.WARNING)
            return
        sync_latest_quotes.delay(symbols, use_cache=False)
        self.message_user(
            request,
            f"Queued quote sync for {len(symbols)} symbols from watchlist items",
            messages.SUCCESS,
        )

    sync_quotes_for_selected_symbols.short_description = "🔄 Sync latest quotes for selected symbols"

    def calculate_indicators_for_selected_symbols(self, request, queryset):
        symbols = _distinct_symbols(queryset)
        for symbol in symbols:
            calculate_indicators_for_symbol.delay(symbol)
        self.message_user(
            request,
            f"Queued indicator calculation for {len(symbols)} symbols from watchlist items",
            messages.SUCCESS,
        )

    calculate_indicators_for_selected_symbols.short_description = "📊 Calculate indicators for selected symbols"

    def invalidate_cache_for_selected_symbols(self, request, queryset):
        symbols = _distinct_symbols(queryset)
        for symbol in symbols:
            MarketDataCache.invalidate_symbol(symbol)
        self.message_user(
            request,
            f"Cleared cache for {len(symbols)} symbols from watchlist items",
            messages.SUCCESS,
        )

    invalidate_cache_for_selected_symbols.short_description = "🗑️ Clear cache for selected symbols"


# Custom admin site configuration
class MarketDataAdminSite(admin.AdminSite):
    """Custom admin site with market data dashboard."""

    site_header = "ShefaFx Market Data Admin"
    site_title = "Market Data Admin"
    index_title = "Market Data Management"