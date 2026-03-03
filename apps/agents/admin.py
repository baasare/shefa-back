"""
Agents admin configuration.
"""
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils import timezone
from apps.agents.models import Agent, AgentRun, AgentDecision, AgentLog
from core.admin_2fa import secure_admin_site


@admin.register(Agent, site=secure_admin_site)
class AgentAdmin(admin.ModelAdmin):
    list_display = ['name', 'user_email', 'agent_type', 'model', 'status_badge',
                    'success_rate', 'last_run_at', 'created_at']
    list_filter = ['agent_type', 'model', 'is_active', 'data_source', 'created_at']
    search_fields = ['name', 'user__email', 'description']
    readonly_fields = ['run_count', 'success_count', 'last_run_at', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    actions = [
        'activate_agents',
        'deactivate_agents',
        'run_agent_analysis',
        'reset_run_stats',
        'duplicate_agent',
    ]

    fieldsets = (
        ('Basic Info', {
            'fields': ('user', 'name', 'description', 'agent_type', 'is_active')
        }),
        ('AI Model Configuration', {
            'fields': ('model', 'temperature', 'max_tokens', 'system_prompt')
        }),
        ('Data Source', {
            'fields': ('data_source', 'data_config')
        }),
        ('Execution Settings', {
            'fields': ('analysis_frequency', 'strategy')
        }),
        ('Statistics', {
            'fields': ('run_count', 'success_count', 'last_run_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def status_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="background-color: #28a745; color: white; padding: 3px 10px; border-radius: 3px;">✓ Active</span>'
            )
        return format_html(
            '<span style="background-color: #6c757d; color: white; padding: 3px 10px; border-radius: 3px;">○ Inactive</span>'
        )
    status_badge.short_description = 'Status'

    def success_rate(self, obj):
        if obj.run_count == 0:
            return '-'
        rate = (obj.success_count / obj.run_count) * 100
        color = '#28a745' if rate >= 80 else '#ffc107' if rate >= 50 else '#dc3545'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}% ({}/{})</span>',
            color, rate, obj.success_count, obj.run_count
        )
    success_rate.short_description = 'Success Rate'

    def activate_agents(self, request, queryset):
        """Activate selected agents."""
        count = 0
        for agent in queryset.filter(is_active=False):
            agent.activate()
            count += 1

        self.message_user(
            request,
            f"Activated {count} agent{'s' if count != 1 else ''}",
            messages.SUCCESS
        )
    activate_agents.short_description = "✅ Activate selected agents"

    def deactivate_agents(self, request, queryset):
        """Deactivate selected agents."""
        count = 0
        for agent in queryset.filter(is_active=True):
            agent.deactivate()
            count += 1

        self.message_user(
            request,
            f"Deactivated {count} agent{'s' if count != 1 else ''}",
            messages.SUCCESS
        )
    deactivate_agents.short_description = "⏸️ Deactivate selected agents"

    def run_agent_analysis(self, request, queryset):
        """Queue agent analysis tasks."""
        # Import here to avoid circular imports
        from apps.agents.tasks import run_custom_agent_analysis

        count = 0
        for agent in queryset:
            if agent.is_active:
                # Queue the task
                run_custom_agent_analysis.delay(str(agent.id))
                count += 1

        self.message_user(
            request,
            f"Queued {count} agent{'s' if count != 1 else ''} for analysis",
            messages.SUCCESS
        )
    run_agent_analysis.short_description = "🚀 Run analysis for selected agents"

    def reset_run_stats(self, request, queryset):
        """Reset run statistics for selected agents."""
        count = queryset.update(
            run_count=0,
            success_count=0,
            last_run_at=None
        )

        self.message_user(
            request,
            f"Reset statistics for {count} agent{'s' if count != 1 else ''}",
            messages.SUCCESS
        )
    reset_run_stats.short_description = "🔄 Reset run statistics"

    def duplicate_agent(self, request, queryset):
        """Duplicate selected agents."""
        count = 0
        for agent in queryset:
            # Create a copy
            agent.pk = None
            agent.id = None
            agent.name = f"{agent.name} (Copy)"
            agent.is_active = False
            agent.run_count = 0
            agent.success_count = 0
            agent.last_run_at = None
            agent.save()
            count += 1

        self.message_user(
            request,
            f"Duplicated {count} agent{'s' if count != 1 else ''}",
            messages.SUCCESS
        )
    duplicate_agent.short_description = "📋 Duplicate selected agents"


@admin.register(AgentRun, site=secure_admin_site)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ['strategy_name', 'status', 'signals_generated', 'duration_seconds', 'started_at']
    list_filter = ['status', 'started_at']
    search_fields = ['strategy__name']
    readonly_fields = ['started_at', 'completed_at', 'duration_seconds']
    date_hierarchy = 'started_at'

    def strategy_name(self, obj):
        return obj.strategy.name
    strategy_name.short_description = 'Strategy'


@admin.register(AgentDecision, site=secure_admin_site)
class AgentDecisionAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'decision', 'confidence', 'strategy_name', 'created_at']
    list_filter = ['decision', 'created_at']
    search_fields = ['symbol', 'strategy__name']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

    def strategy_name(self, obj):
        return obj.strategy.name
    strategy_name.short_description = 'Strategy'


@admin.register(AgentLog, site=secure_admin_site)
class AgentLogAdmin(admin.ModelAdmin):
    list_display = ['level', 'message_preview', 'created_at']
    list_filter = ['level', 'created_at']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

    def message_preview(self, obj):
        return obj.message[:100]
    message_preview.short_description = 'Message'
