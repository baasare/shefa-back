"""
Brokers admin configuration.
"""
from django.contrib import admin
from .models import BrokerConnection


@admin.register(BrokerConnection)
class BrokerConnectionAdmin(admin.ModelAdmin):
    list_display = ['user_email', 'broker', 'status', 'is_paper_trading', 'last_sync_at']
    list_filter = ['broker', 'status', 'is_paper_trading']
    search_fields = ['user__email', 'account_number']
    readonly_fields = ['created_at', 'updated_at', 'last_sync_at']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
