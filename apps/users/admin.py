"""
User admin configuration for ShefaAI Trading Platform.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from apps.users.models import User, UserProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Enhanced User admin with custom fields."""

    list_display = [
        'email', 'display_name', 'risk_tolerance_badge', 'experience_level',
        'is_verified', 'is_active', 'created_at'
    ]
    list_filter = [
        'is_active', 'is_verified', 'is_staff', 'risk_tolerance',
        'experience_level', 'mfa_enabled', 'created_at'
    ]
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['-created_at']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'phone_number')
        }),
        ('Trading Preferences', {
            'fields': ('risk_tolerance', 'experience_level', 'approval_threshold')
        }),
        ('Security', {
            'fields': ('mfa_enabled', 'mfa_secret')
        }),
        ('Notifications', {
            'fields': ('email_notifications', 'push_notifications', 'sms_notifications'),
            'classes': ('collapse',)
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_verified', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important Dates', {
            'fields': ('last_login', 'created_at', 'updated_at', 'last_login_ip'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name'),
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def risk_tolerance_badge(self, obj):
        colors = {
            'conservative': '#28a745',
            'moderate': '#ffc107',
            'aggressive': '#dc3545'
        }
        color = colors.get(obj.risk_tolerance, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_risk_tolerance_display()
        )
    risk_tolerance_badge.short_description = 'Risk Tolerance'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """User Profile admin."""

    list_display = ['user', 'timezone', 'default_paper_trading', 'max_daily_loss_pct', 'created_at']
    list_filter = ['timezone', 'default_paper_trading', 'created_at']
    search_fields = ['user__email']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Trading Goals', {
            'fields': ('investment_goals', 'time_horizon', 'preferred_asset_classes')
        }),
        ('Settings', {
            'fields': ('timezone', 'default_paper_trading')
        }),
        ('Risk Parameters', {
            'fields': ('max_daily_loss_pct', 'max_position_size_pct')
        }),
        ('Profile', {
            'fields': ('avatar_url', 'bio')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
