"""
Agents admin configuration.
"""
from django.contrib import admin
from .models import AgentRun, AgentDecision, AgentLog


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ['strategy_name', 'status', 'signals_generated', 'duration_seconds', 'started_at']
    list_filter = ['status', 'started_at']
    search_fields = ['strategy__name']
    readonly_fields = ['started_at', 'completed_at', 'duration_seconds']
    date_hierarchy = 'started_at'

    def strategy_name(self, obj):
        return obj.strategy.name
    strategy_name.short_description = 'Strategy'


@admin.register(AgentDecision)
class AgentDecisionAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'decision', 'confidence', 'strategy_name', 'created_at']
    list_filter = ['decision', 'created_at']
    search_fields = ['symbol', 'strategy__name']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

    def strategy_name(self, obj):
        return obj.strategy.name
    strategy_name.short_description = 'Strategy'


@admin.register(AgentLog)
class AgentLogAdmin(admin.ModelAdmin):
    list_display = ['level', 'message_preview', 'created_at']
    list_filter = ['level', 'created_at']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

    def message_preview(self, obj):
        return obj.message[:100]
    message_preview.short_description = 'Message'
