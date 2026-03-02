"""
Views for Agents, Market Data, Brokers, and Notifications.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.notifications.models import Notification
from apps.notifications.serializers import (
    NotificationSerializer, NotificationListSerializer
)


class NotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for Notification CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return NotificationListSerializer
        return NotificationSerializer
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark notification as read."""
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        
        serializer = self.get_serializer(notification)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read."""
        notifications = self.get_queryset().filter(is_read=False)
        count = notifications.update(is_read=True, read_at=timezone.now())
        
        return Response({
            'message': f'{count} notifications marked as read'
        })
    
    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Get unread notifications."""
        notifications = self.get_queryset().filter(is_read=False)
        serializer = self.get_serializer(notifications, many=True)
        
        return Response({
            'count': notifications.count(),
            'notifications': serializer.data
        })
