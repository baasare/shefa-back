"""
Agent models for ShefaAI Trading Platform.
"""
from django.db import models
import uuid


class AgentRun(models.Model):
    """Record of agent analysis execution."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    strategy = models.ForeignKey('strategies.Strategy', on_delete=models.CASCADE, related_name='agent_runs')
    symbols = models.JSONField('Symbols Analyzed', default=list)

    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField('Started At', auto_now_add=True)
    completed_at = models.DateTimeField('Completed At', null=True, blank=True)
    duration_seconds = models.IntegerField('Duration (seconds)', null=True, blank=True)

    # Results
    signals_generated = models.IntegerField('Signals Generated', default=0)
    errors = models.JSONField('Errors', null=True, blank=True)

    class Meta:
        db_table = 'agent_runs'
        verbose_name = 'Agent Run'
        verbose_name_plural = 'Agent Runs'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['strategy', '-started_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.strategy.name} - {self.started_at}'


class AgentDecision(models.Model):
    """Individual agent decision for a symbol."""

    DECISION_CHOICES = [
        ('buy', 'Buy'),
        ('sell', 'Sell'),
        ('hold', 'Hold'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='decisions')
    strategy = models.ForeignKey('strategies.Strategy', on_delete=models.CASCADE, related_name='decisions')
    symbol = models.CharField('Symbol', max_length=20, db_index=True)

    decision = models.CharField('Decision', max_length=10, choices=DECISION_CHOICES)
    confidence = models.DecimalField('Confidence Score', max_digits=5, decimal_places=2, null=True, blank=True)

    # Analysis Results
    technical_analysis = models.JSONField('Technical Analysis', null=True, blank=True)
    fundamental_analysis = models.JSONField('Fundamental Analysis', null=True, blank=True)
    sentiment_analysis = models.JSONField('Sentiment Analysis', null=True, blank=True)
    risk_assessment = models.JSONField('Risk Assessment', null=True, blank=True)

    # Trade Signal (if generated)
    trade_signal = models.JSONField('Trade Signal', null=True, blank=True)
    rationale = models.TextField('Rationale', blank=True)

    created_at = models.DateTimeField('Created At', auto_now_add=True)

    class Meta:
        db_table = 'agent_decisions'
        verbose_name = 'Agent Decision'
        verbose_name_plural = 'Agent Decisions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['symbol', '-created_at']),
            models.Index(fields=['strategy', '-created_at']),
        ]

    def __str__(self):
        return f'{self.symbol} - {self.decision.upper()} ({self.confidence}%)'


class AgentLog(models.Model):
    """Detailed agent execution logs for debugging."""

    LOG_LEVEL_CHOICES = [
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name='logs')
    agent_decision = models.ForeignKey(
        AgentDecision,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )

    level = models.CharField('Level', max_length=20, choices=LOG_LEVEL_CHOICES)
    message = models.TextField('Message')
    data = models.JSONField('Data', null=True, blank=True)

    created_at = models.DateTimeField('Created At', auto_now_add=True)

    class Meta:
        db_table = 'agent_logs'
        verbose_name = 'Agent Log'
        verbose_name_plural = 'Agent Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['agent_run', '-created_at']),
            models.Index(fields=['level']),
        ]

    def __str__(self):
        return f'[{self.level.upper()}] {self.message[:50]}'
