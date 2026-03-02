"""
Agent serializers for ShefaAI Trading Platform.
"""
from rest_framework import serializers
from .models import AgentRun, AgentDecision, AgentLog


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
