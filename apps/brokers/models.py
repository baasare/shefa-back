"""
Broker models for ShefaFx Trading Platform.
"""
import uuid
from django.db import models
from apps.brokers.encryption import decrypt_api_key


class BrokerConnection(models.Model):
    """User's broker API connection."""

    BROKER_CHOICES = [
        ('alpaca', 'Alpaca'),
        ('alpaca_paper', 'Alpaca (Paper)'),
        ('interactive_brokers', 'Interactive Brokers'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='broker_connections')
    portfolio = models.OneToOneField(
        'portfolios.Portfolio',
        on_delete=models.CASCADE,
        related_name='broker_connection',
        null=True,
        blank=True
    )

    broker = models.CharField('Broker', max_length=50, choices=BROKER_CHOICES)
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='inactive')

    # Encrypted API Credentials
    api_key_encrypted = models.TextField('API Key (Encrypted)')
    api_secret_encrypted = models.TextField('API Secret (Encrypted)', blank=True)

    # Connection Info
    account_number = models.CharField('Account Number', max_length=100, blank=True)
    is_paper_trading = models.BooleanField('Paper Trading', default=True)

    last_sync_at = models.DateTimeField('Last Sync', null=True, blank=True)
    last_error = models.TextField('Last Error', blank=True)

    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)

    class Meta:
        db_table = 'broker_connections'
        verbose_name = 'Broker Connection'
        verbose_name_plural = 'Broker Connections'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} - {self.broker}'

    def get_decrypted_credentials(self):
        """
        Get decrypted API credentials.

        Returns:
            dict: {'api_key': str, 'api_secret': str}
        """
        return {
            'api_key': decrypt_api_key(self.api_key_encrypted) if self.api_key_encrypted else '',
            'api_secret': decrypt_api_key(self.api_secret_encrypted) if self.api_secret_encrypted else ''
        }
