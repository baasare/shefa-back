"""
Strategy admin configuration.
"""
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils import timezone
from apps.strategies.models import Strategy, Backtest
from apps.strategies.tasks import (
    execute_strategy_task,
    execute_all_active_strategies,
    run_backtest_task,
    validate_strategy_task,
    update_strategy_performance_metrics,
    cleanup_old_backtests
)
from apps.strategies.services import calculate_strategy_performance
from core.admin_2fa import secure_admin_site


@admin.register(Strategy, site=secure_admin_site)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ['name', 'user_email', 'strategy_type', 'status_badge',
                    'win_rate', 'total_pnl_display', 'created_at']
    list_filter = ['strategy_type', 'status', 'created_at']
    search_fields = ['name', 'user__email']
    readonly_fields = ['total_trades', 'winning_trades', 'win_rate', 'total_pnl',
                       'sharpe_ratio', 'created_at', 'updated_at', 'activated_at']
    date_hierarchy = 'created_at'
    actions = [
        'activate_strategies',
        'pause_strategies',
        'execute_strategies_dry_run',
        'execute_strategies_live',
        'validate_strategies',
        'update_performance_metrics',
        'calculate_current_performance'
    ]

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

    def activate_strategies(self, request, queryset):
        """Activate selected strategies."""
        count = 0
        for strategy in queryset:
            if strategy.status != 'active':
                strategy.status = 'active'
                strategy.activated_at = timezone.now()
                strategy.save()
                count += 1

        self.message_user(
            request,
            f"Activated {count} strateg{'y' if count == 1 else 'ies'}",
            messages.SUCCESS
        )
    activate_strategies.short_description = "✅ Activate selected strategies"

    def pause_strategies(self, request, queryset):
        """Pause selected strategies."""
        count = queryset.update(status='paused')

        self.message_user(
            request,
            f"Paused {count} strateg{'y' if count == 1 else 'ies'}",
            messages.SUCCESS
        )
    pause_strategies.short_description = "⏸️ Pause selected strategies"

    def execute_strategies_dry_run(self, request, queryset):
        """Execute strategies in dry-run mode (no real orders)."""
        count = 0
        for strategy in queryset:
            # Queue execution task
            execute_strategy_task.delay(
                strategy_id=str(strategy.id),
                dry_run=True
            )
            count += 1

        self.message_user(
            request,
            f"Queued {count} strateg{'y' if count == 1 else 'ies'} for dry-run execution",
            messages.SUCCESS
        )
    execute_strategies_dry_run.short_description = "🔍 Execute (Dry Run - No Orders)"

    def execute_strategies_live(self, request, queryset):
        """Execute strategies in live mode (places real orders)."""
        # Only allow active strategies
        active_strategies = queryset.filter(status='active')

        if not active_strategies.exists():
            self.message_user(
                request,
                "No active strategies selected. Only active strategies can be executed live.",
                messages.WARNING
            )
            return

        count = 0
        for strategy in active_strategies:
            # Queue execution task
            execute_strategy_task.delay(
                strategy_id=str(strategy.id),
                dry_run=False
            )
            count += 1

        self.message_user(
            request,
            f"⚠️ Queued {count} strateg{'y' if count == 1 else 'ies'} for LIVE execution (real orders will be placed)",
            messages.WARNING
        )
    execute_strategies_live.short_description = "🚀 Execute (LIVE - Real Orders)"

    def validate_strategies(self, request, queryset):
        """Validate strategy configurations."""
        count = 0
        for strategy in queryset:
            # Queue validation task
            validate_strategy_task.delay(str(strategy.id))
            count += 1

        self.message_user(
            request,
            f"Queued {count} strateg{'y' if count == 1 else 'ies'} for validation. Check Celery logs for results.",
            messages.SUCCESS
        )
    validate_strategies.short_description = "✓ Validate configurations"

    def update_performance_metrics(self, request, queryset):
        """Update performance metrics from trade history."""
        count = 0
        for strategy in queryset:
            # Queue performance update task
            update_strategy_performance_metrics.delay(str(strategy.id))
            count += 1

        self.message_user(
            request,
            f"Queued performance metrics update for {count} strateg{'y' if count == 1 else 'ies'}",
            messages.SUCCESS
        )
    update_performance_metrics.short_description = "📊 Update performance metrics"

    def calculate_current_performance(self, request, queryset):
        """Calculate and display current performance (synchronous)."""
        results = []

        for strategy in queryset:
            metrics = calculate_strategy_performance(strategy)

            # Update the strategy with calculated metrics
            strategy.total_trades = metrics['total_trades']
            strategy.winning_trades = metrics['winning_trades']
            strategy.win_rate = metrics['win_rate']
            strategy.total_pnl = metrics['total_pnl']
            strategy.save()

            results.append(f"{strategy.name}: {metrics['total_trades']} trades, ${metrics['total_pnl']:.2f} P&L")

        if results:
            message = "Updated performance: " + " | ".join(results[:3])
            if len(results) > 3:
                message += f" ... and {len(results) - 3} more"
        else:
            message = "No performance data to calculate"

        self.message_user(request, message, messages.SUCCESS)
    calculate_current_performance.short_description = "💹 Calculate & update performance now"


@admin.register(Backtest, site=secure_admin_site)
class BacktestAdmin(admin.ModelAdmin):
    list_display = ['strategy_name', 'start_date', 'end_date', 'status_badge',
                    'total_return', 'sharpe_ratio', 'win_rate', 'created_at']
    list_filter = ['status', 'start_date', 'created_at']
    search_fields = ['strategy__name']
    readonly_fields = ['created_at', 'completed_at']
    date_hierarchy = 'created_at'
    actions = [
        'rerun_backtests',
        'delete_old_completed_backtests'
    ]

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

    def rerun_backtests(self, request, queryset):
        """Rerun selected backtests with same parameters."""
        count = 0
        for backtest in queryset:
            # Queue new backtest with same parameters
            run_backtest_task.delay(
                strategy_id=str(backtest.strategy.id),
                start_date_str=backtest.start_date.isoformat(),
                end_date_str=backtest.end_date.isoformat(),
                initial_capital=str(backtest.initial_capital)
            )
            count += 1

        self.message_user(
            request,
            f"Queued {count} backtest{'s' if count != 1 else ''} for re-execution",
            messages.SUCCESS
        )
    rerun_backtests.short_description = "🔄 Rerun selected backtests"

    def delete_old_completed_backtests(self, request, queryset):
        """Delete old completed backtests."""
        from datetime import timedelta

        # Only delete completed backtests older than 90 days
        cutoff_date = timezone.now() - timedelta(days=90)
        old_backtests = queryset.filter(
            status='completed',
            created_at__lt=cutoff_date
        )

        count = old_backtests.count()

        if count == 0:
            self.message_user(
                request,
                "No completed backtests older than 90 days found",
                messages.WARNING
            )
            return

        old_backtests.delete()

        self.message_user(
            request,
            f"Deleted {count} old completed backtest{'s' if count != 1 else ''}",
            messages.SUCCESS
        )
    delete_old_completed_backtests.short_description = "🗑️ Delete old completed backtests (>90 days)"
