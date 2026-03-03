"""
Agent models for ShefaFx Trading Platform.
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
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


class Agent(models.Model):
    """
    User-created AI agent configuration.

    Allows users to create custom AI agents with specific models,
    data sources, and configurations for automated trading analysis.
    """

    MODEL_CHOICES = [
        ('claude-3-opus', 'Claude 3 Opus'),
        ('claude-3-sonnet', 'Claude 3 Sonnet'),
        ('claude-3-haiku', 'Claude 3 Haiku'),
        ('gpt-4', 'GPT-4'),
        ('gpt-4-turbo', 'GPT-4 Turbo'),
        ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
    ]

    AGENT_TYPE_CHOICES = [
        ('technical', 'Technical Analysis'),
        ('fundamental', 'Fundamental Analysis'),
        ('sentiment', 'Sentiment Analysis'),
        ('risk', 'Risk Management'),
        ('general', 'General Purpose'),
    ]

    DATA_SOURCE_CHOICES = [
        ('polygon', 'Polygon.io (Massive.com)'),
        ('alpha_vantage', 'Alpha Vantage'),
        ('yahoo_finance', 'Yahoo Finance'),
        ('all', 'All Sources'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='custom_agents')

    # Agent Configuration
    name = models.CharField('Agent Name', max_length=100)
    description = models.TextField('Description', blank=True)
    agent_type = models.CharField('Agent Type', max_length=20, choices=AGENT_TYPE_CHOICES, default='general')

    # AI Model Settings
    model = models.CharField('AI Model', max_length=50, choices=MODEL_CHOICES, default='claude-3-sonnet')
    temperature = models.DecimalField(
        'Temperature',
        max_digits=3,
        decimal_places=2,
        default=0.70,
        validators=[MinValueValidator(0.0), MaxValueValidator(2.0)],
        help_text='Controls randomness in responses (0.0 = deterministic, 2.0 = very creative)'
    )
    max_tokens = models.IntegerField(
        'Max Tokens',
        default=4000,
        validators=[MinValueValidator(100), MaxValueValidator(100000)],
        help_text='Maximum length of AI response'
    )

    # Data Source Configuration
    data_source = models.CharField('Data Source', max_length=50, choices=DATA_SOURCE_CHOICES, default='polygon')
    data_config = models.JSONField(
        'Data Configuration',
        default=dict,
        blank=True,
        help_text='Additional configuration for data sources (e.g., indicators, timeframes)'
    )

    # Agent Behavior
    system_prompt = models.TextField(
        'System Prompt',
        blank=True,
        help_text='Custom instructions for the AI agent'
    )
    analysis_frequency = models.IntegerField(
        'Analysis Frequency (minutes)',
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
        help_text='How often the agent should run analysis (5-1440 minutes)'
    )

    # Status and Execution
    is_active = models.BooleanField('Active', default=False)
    run_count = models.IntegerField('Total Runs', default=0, editable=False)
    success_count = models.IntegerField('Successful Runs', default=0, editable=False)
    last_run_at = models.DateTimeField('Last Run', null=True, blank=True, editable=False)

    # Associated Strategy (optional)
    strategy = models.ForeignKey(
        'strategies.Strategy',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='custom_agents',
        help_text='Link agent to a specific strategy'
    )

    # Metadata
    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)

    class Meta:
        db_table = 'custom_agents'
        verbose_name = 'Agent'
        verbose_name_plural = 'Agents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['is_active']),
            models.Index(fields=['agent_type']),
        ]

    def __str__(self):
        return f'{self.name} ({self.user.email}) - {self.model}'

    def activate(self):
        """Activate the agent."""
        self.is_active = True
        self.save(update_fields=['is_active', 'updated_at'])

    def deactivate(self):
        """Deactivate the agent."""
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

    def record_run(self, success=True):
        """Record an agent run."""
        from django.utils import timezone
        self.run_count += 1
        if success:
            self.success_count += 1
        self.last_run_at = timezone.now()
        self.save(update_fields=['run_count', 'success_count', 'last_run_at', 'updated_at'])
