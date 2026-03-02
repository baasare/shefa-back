"""
Notification service utilities.
"""
from typing import Dict, Any, Optional
from apps.notifications.models import Notification


def create_notification(
    user,
    notification_type: str,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None
) -> Notification:
    """
    Create a notification.

    Args:
        user: User instance
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        data: Optional additional data

    Returns:
        Created Notification instance
    """
    return Notification.objects.create(
        user=user,
        type=notification_type,
        title=title,
        message=message,
        data=data or {}
    )


def mark_as_read(notification_id: int) -> bool:
    """Mark notification as read."""
    try:
        notification = Notification.objects.get(id=notification_id)
        notification.is_read = True
        notification.save()
        return True
    except Notification.DoesNotExist:
        return False


def get_unread_count(user) -> int:
    """Get count of unread notifications."""
    return Notification.objects.filter(user=user, is_read=False).count()
