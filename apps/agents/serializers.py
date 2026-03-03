"""
Agent serializers for ShefaFx Trading Platform.
"""
from rest_framework import serializers
from apps.agents.models import AgentRun, AgentDecision, AgentLog, Agent


class AgentLogSerializer(serializers.ModelSerializer):
    """Serializer for AgentLog model."""
    
    class Meta:
        model = AgentLog
        fields = ['id', 'agent_run', 'agent_decision', 'level', 'message', 'data', 'created_at']
        read_only_fields = ['id', 'created_at']


class AgentDecisionSerializer(serializers.ModelSerializer):
    """Serializer for AgentDecision model."""
    
    strategy_name = serializers.CharField(source='strategy.name', read_only=True)
    confidence_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AgentDecision
        fields = [
            'id', 'agent_run', 'strategy', 'strategy_name', 'symbol',
            'decision', 'confidence', 'confidence_display',
            'technical_analysis', 'fundamental_analysis',
            'sentiment_analysis', 'risk_assessment',
            'trade_signal', 'rationale', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_confidence_display(self, obj):
        """Format confidence score."""
        if obj.confidence is None:
            return None
        return {
            'score': float(obj.confidence),
            'level': self._get_confidence_level(float(obj.confidence))
        }
    
    def _get_confidence_level(self, score):
        """Get confidence level from score."""
        if score >= 80:
            return 'high'
        elif score >= 60:
            return 'medium'
        else:
            return 'low'


class AgentRunSerializer(serializers.ModelSerializer):
    """Serializer for AgentRun model."""
    
    strategy_name = serializers.CharField(source='strategy.name', read_only=True)
    decisions = AgentDecisionSerializer(many=True, read_only=True)
    duration_display = serializers.SerializerMethodField()
    
    class Meta:
        model = AgentRun
        fields = [
            'id', 'strategy', 'strategy_name', 'symbols', 'status',
            'started_at', 'completed_at', 'duration_seconds', 'duration_display',
            'signals_generated', 'errors', 'decisions'
        ]
        read_only_fields = ['id', 'started_at', 'completed_at', 'duration_seconds']
    
    def get_duration_display(self, obj):
        """Format duration for display."""
        if obj.duration_seconds is None:
            return None

        minutes = obj.duration_seconds // 60
        seconds = obj.duration_seconds % 60
        return f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"


class AgentSerializer(serializers.ModelSerializer):
    """Serializer for custom Agent model."""

    strategy_name = serializers.CharField(source='strategy.name', read_only=True)
    success_rate = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Agent
        fields = [
            'id', 'user', 'name', 'description', 'agent_type',
            'model', 'temperature', 'max_tokens',
            'data_source', 'data_config', 'system_prompt',
            'analysis_frequency', 'is_active', 'run_count',
            'success_count', 'success_rate', 'last_run_at',
            'strategy', 'strategy_name', 'status',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'run_count', 'success_count',
            'last_run_at', 'created_at', 'updated_at'
        ]

    def get_success_rate(self, obj):
        """Calculate success rate percentage."""
        if obj.run_count == 0:
            return 0.0
        return round((obj.success_count / obj.run_count) * 100, 2)

    def get_status(self, obj):
        """Get human-readable status."""
        if not obj.is_active:
            return 'inactive'
        if obj.last_run_at is None:
            return 'ready'
        return 'running'

    def create(self, validated_data):
        """Set user from request context."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['user'] = request.user
        return super().create(validated_data)


class AgentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new Agent."""

    class Meta:
        model = Agent
        fields = [
            'name', 'description', 'agent_type',
            'model', 'temperature', 'max_tokens',
            'data_source', 'data_config', 'system_prompt',
            'analysis_frequency', 'strategy'
        ]

    def create(self, validated_data):
        """Set user from request context."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['user'] = request.user
        return super().create(validated_data)


class AgentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating an Agent."""

    class Meta:
        model = Agent
        fields = [
            'name', 'description', 'agent_type',
            'model', 'temperature', 'max_tokens',
            'data_source', 'data_config', 'system_prompt',
            'analysis_frequency', 'strategy'
        ]
