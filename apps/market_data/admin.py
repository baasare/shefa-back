"""
Market Data admin configuration.
"""
from django.contrib import admin
from .models import Quote, Indicator


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'source']
    list_filter = ['symbol', 'source', 'timestamp']
    search_fields = ['symbol']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'indicator_type', 'value', 'timestamp']
    list_filter = ['indicator_type', 'timestamp']
    search_fields = ['symbol']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'
