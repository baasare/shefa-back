# Generated manually for Agent model

import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0002_initial'),
        ('strategies', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Agent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, verbose_name='Agent Name')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
                ('agent_type', models.CharField(
                    choices=[
                        ('technical', 'Technical Analysis'),
                        ('fundamental', 'Fundamental Analysis'),
                        ('sentiment', 'Sentiment Analysis'),
                        ('risk', 'Risk Management'),
                        ('general', 'General Purpose')
                    ],
                    default='general',
                    max_length=20,
                    verbose_name='Agent Type'
                )),
                ('model', models.CharField(
                    choices=[
                        ('claude-3-opus', 'Claude 3 Opus'),
                        ('claude-3-sonnet', 'Claude 3 Sonnet'),
                        ('claude-3-haiku', 'Claude 3 Haiku'),
                        ('gpt-4', 'GPT-4'),
                        ('gpt-4-turbo', 'GPT-4 Turbo'),
                        ('gpt-3.5-turbo', 'GPT-3.5 Turbo')
                    ],
                    default='claude-3-sonnet',
                    max_length=50,
                    verbose_name='AI Model'
                )),
                ('temperature', models.DecimalField(
                    decimal_places=2,
                    default=0.70,
                    help_text='Controls randomness in responses (0.0 = deterministic, 2.0 = very creative)',
                    max_digits=3,
                    validators=[
                        django.core.validators.MinValueValidator(0.0),
                        django.core.validators.MaxValueValidator(2.0)
                    ],
                    verbose_name='Temperature'
                )),
                ('max_tokens', models.IntegerField(
                    default=4000,
                    help_text='Maximum length of AI response',
                    validators=[
                        django.core.validators.MinValueValidator(100),
                        django.core.validators.MaxValueValidator(100000)
                    ],
                    verbose_name='Max Tokens'
                )),
                ('data_source', models.CharField(
                    choices=[
                        ('polygon', 'Polygon.io (Massive.com)'),
                        ('alpha_vantage', 'Alpha Vantage'),
                        ('yahoo_finance', 'Yahoo Finance'),
                        ('all', 'All Sources')
                    ],
                    default='polygon',
                    max_length=50,
                    verbose_name='Data Source'
                )),
                ('data_config', models.JSONField(
                    blank=True,
                    default=dict,
                    help_text='Additional configuration for data sources (e.g., indicators, timeframes)',
                    verbose_name='Data Configuration'
                )),
                ('system_prompt', models.TextField(
                    blank=True,
                    help_text='Custom instructions for the AI agent',
                    verbose_name='System Prompt'
                )),
                ('analysis_frequency', models.IntegerField(
                    default=30,
                    help_text='How often the agent should run analysis (5-1440 minutes)',
                    validators=[
                        django.core.validators.MinValueValidator(5),
                        django.core.validators.MaxValueValidator(1440)
                    ],
                    verbose_name='Analysis Frequency (minutes)'
                )),
                ('is_active', models.BooleanField(default=False, verbose_name='Active')),
                ('run_count', models.IntegerField(default=0, editable=False, verbose_name='Total Runs')),
                ('success_count', models.IntegerField(default=0, editable=False, verbose_name='Successful Runs')),
                ('last_run_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='Last Run')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('strategy', models.ForeignKey(
                    blank=True,
                    help_text='Link agent to a specific strategy',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='custom_agents',
                    to='strategies.strategy'
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='custom_agents',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Agent',
                'verbose_name_plural': 'Agents',
                'db_table': 'custom_agents',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='agent',
            index=models.Index(fields=['user', '-created_at'], name='custom_agen_user_id_5c2a2f_idx'),
        ),
        migrations.AddIndex(
            model_name='agent',
            index=models.Index(fields=['is_active'], name='custom_agen_is_acti_1e2b3c_idx'),
        ),
        migrations.AddIndex(
            model_name='agent',
            index=models.Index(fields=['agent_type'], name='custom_agen_agent_t_4d5e6f_idx'),
        ),
    ]
