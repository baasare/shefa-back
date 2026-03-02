"""
Notification serializers for ShefaAI Trading Platform.
"""
from rest_framework import serializers
from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model."""
    
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_email', 'notification_type',
            'title', 'message', 'data', 'send_email', 'send_push',
            'send_sms', 'status', 'is_read', 'created_at',
            'sent_at', 'read_at'
        ]
        read_only_fields = [
            'id', 'user', 'status', 'created_at', 'sent_at', 'read_at'
        ]
    
    def create(self, validated_data):
        """Create notification with user from request."""
        validated_data['user'] = self.context['request'].user
        validated_data['status'] = 'pending'
        return super().create(validated_data)


class NotificationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for notification lists."""
    
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'title', 'message',
            'is_read', 'created_at'
        ]
