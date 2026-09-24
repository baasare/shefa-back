import re

from rest_framework import serializers

from apps.bots.models import Bot, BotEvent, BotRun


SYMBOL_RE = re.compile(r'^[A-Z][A-Z0-9.-]{0,5}$')


class BotSerializer(serializers.ModelSerializer):
    portfolio_mode = serializers.CharField(source='portfolio.portfolio_type', read_only=True)
    last_run_status = serializers.SerializerMethodField()

    class Meta:
        model = Bot
        fields = [
            'id', 'name', 'idea', 'symbols', 'portfolio', 'portfolio_mode', 'status',
            'max_order_value', 'max_open_positions', 'daily_loss_limit_pct',
            'run_frequency_minutes', 'config_version', 'next_run_at', 'last_run_at',
            'last_run_status', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'portfolio', 'portfolio_mode', 'status', 'config_version',
            'next_run_at', 'last_run_at', 'last_run_status', 'created_at', 'updated_at',
        ]

    def validate_symbols(self, value):
        if not isinstance(value, list) or not 1 <= len(value) <= 10:
            raise serializers.ValidationError('Choose between 1 and 10 U.S. stock or ETF symbols.')
        normalized = []
        for symbol in value:
            if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol.strip().upper()):
                raise serializers.ValidationError('Use simple U.S. stock/ETF ticker symbols only.')
            ticker = symbol.strip().upper()
            if ticker not in normalized:
                normalized.append(ticker)
        return normalized

    def validate_max_order_value(self, value):
        if value < 1 or value > 1000:
            raise serializers.ValidationError('Order limit must be between $1 and $1,000.')
        return value

    def validate_max_open_positions(self, value):
        if not 1 <= value <= 10:
            raise serializers.ValidationError('Open positions must be between 1 and 10.')
        return value

    def validate_daily_loss_limit_pct(self, value):
        if value <= 0 or value > 5:
            raise serializers.ValidationError('Daily loss limit must be greater than 0% and at most 5%.')
        return value

    def validate_run_frequency_minutes(self, value):
        if value not in (15, 30, 60):
            raise serializers.ValidationError('Run frequency must be 15, 30, or 60 minutes.')
        return value

    def validate_idea(self, value):
        value = value.strip()
        if not value or len(value) > 2000:
            raise serializers.ValidationError('Describe the bot in 1 to 2,000 characters.')
        return value

    def get_last_run_status(self, obj):
        run = obj.runs.first()
        return run.status if run else None

    def update(self, instance, validated_data):
        if instance.status == 'active':
            raise serializers.ValidationError('Pause the bot before changing its rules.')
        instance.config_version += 1
        return super().update(instance, validated_data)


class BotRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotRun
        fields = ['id', 'bot', 'status', 'result', 'error_message', 'queued_at', 'started_at', 'completed_at']
        read_only_fields = fields


class BotEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = BotEvent
        fields = ['id', 'run', 'event_type', 'message', 'data', 'created_at']
        read_only_fields = fields


class BotDraftRequestSerializer(serializers.Serializer):
    idea = serializers.CharField(min_length=1, max_length=2000, trim_whitespace=True)
