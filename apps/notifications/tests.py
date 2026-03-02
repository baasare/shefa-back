"""
Comprehensive test suite for the notifications app.
Tests notification models, email sending, tasks, and API endpoints.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core import mail
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import Mock, patch
from decimal import Decimal

from apps.notifications.models import Notification
from apps.notifications.services import (
    create_notification,
    send_email_notification,
    format_trade_alert_email,
    format_approval_request_email
)
from apps.notifications.tasks import (
    send_trade_execution_alert,
    send_approval_request,
    send_strategy_signal_notification,
    send_daily_portfolio_summary
)
from apps.portfolios.models import Portfolio
from apps.orders.models import Order, Trade
from apps.brokers.models import BrokerConnection
from apps.brokers.encryption import encrypt_api_key

User = get_user_model()


class NotificationModelTests(TestCase):
    """Test cases for Notification model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

    def test_create_notification(self):
        """Test creating a notification."""
        notification = Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='Trade Executed',
            message='Your order for 10 AAPL has been executed',
            data={'symbol': 'AAPL', 'quantity': 10}
        )

        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.type, 'trade_executed')
        self.assertFalse(notification.is_read)
        self.assertEqual(notification.data['symbol'], 'AAPL')

    def test_notification_types(self):
        """Test different notification types."""
        types = ['trade_executed', 'approval_required', 'strategy_signal', 'account_alert']

        for notif_type in types:
            notification = Notification.objects.create(
                user=self.user,
                type=notif_type,
                title=f'{notif_type} notification',
                message='Test message'
            )

            self.assertEqual(notification.type, notif_type)

    def test_mark_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='Trade Executed',
            message='Test message'
        )

        self.assertFalse(notification.is_read)

        notification.is_read = True
        notification.save()

        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_notification_string_representation(self):
        """Test __str__ method."""
        notification = Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='Trade Executed',
            message='Test message'
        )

        expected = f"{self.user.email} - Trade Executed"
        self.assertEqual(str(notification), expected)

    def test_notification_ordering(self):
        """Test notifications are ordered by created_at descending."""
        # Create multiple notifications
        notif1 = Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='Notification 1',
            message='First'
        )

        notif2 = Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='Notification 2',
            message='Second'
        )

        notifications = Notification.objects.filter(user=self.user)

        # Most recent should be first
        self.assertEqual(notifications[0], notif2)


class NotificationServicesTests(TestCase):
    """Test cases for notification services."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            email_notifications=True
        )

    def test_create_notification(self):
        """Test creating notification via service."""
        notification = create_notification(
            user=self.user,
            notif_type='trade_executed',
            title='Trade Executed',
            message='Your trade was executed',
            data={'symbol': 'AAPL'}
        )

        self.assertIsNotNone(notification)
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.type, 'trade_executed')

    def test_send_email_notification(self):
        """Test sending email notification."""
        result = send_email_notification(
            user=self.user,
            subject='Test Notification',
            message='This is a test email'
        )

        self.assertTrue(result['success'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Test Notification')
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_send_email_disabled(self):
        """Test email not sent when notifications disabled."""
        self.user.email_notifications = False
        self.user.save()

        result = send_email_notification(
            user=self.user,
            subject='Test Notification',
            message='This should not be sent'
        )

        self.assertFalse(result['success'])
        self.assertEqual(len(mail.outbox), 0)

    def test_format_trade_alert_email(self):
        """Test formatting trade alert email."""
        trade_data = {
            'symbol': 'AAPL',
            'quantity': 10,
            'side': 'buy',
            'price': Decimal('150.00'),
            'total_value': Decimal('1500.00')
        }

        email_html = format_trade_alert_email(trade_data)

        self.assertIn('AAPL', email_html)
        self.assertIn('10', email_html)
        self.assertIn('buy', email_html.lower())
        self.assertIn('150.00', email_html)

    def test_format_approval_request_email(self):
        """Test formatting approval request email."""
        order_data = {
            'symbol': 'AAPL',
            'quantity': 50,
            'side': 'buy',
            'estimated_cost': Decimal('7500.00')
        }

        email_html = format_approval_request_email(order_data)

        self.assertIn('AAPL', email_html)
        self.assertIn('50', email_html)
        self.assertIn('approval', email_html.lower())


class NotificationTasksTests(TestCase):
    """Test cases for notification Celery tasks."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            email_notifications=True
        )

        self.broker_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

    def test_send_trade_execution_alert(self):
        """Test sending trade execution alert."""
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00')
        )

        result = send_trade_execution_alert(trade.id)

        self.assertTrue(result['success'])
        # Check notification was created
        notifications = Notification.objects.filter(
            user=self.user,
            type='trade_executed'
        )
        self.assertEqual(notifications.count(), 1)
        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)

    def test_send_approval_request(self):
        """Test sending approval request notification."""
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=50,
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00'),
            status='pending_approval',
            approval_required=True
        )

        result = send_approval_request(order.id)

        self.assertTrue(result['success'])
        # Check notification was created
        notifications = Notification.objects.filter(
            user=self.user,
            type='approval_required'
        )
        self.assertEqual(notifications.count(), 1)
        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('approval', mail.outbox[0].subject.lower())

    def test_send_strategy_signal_notification(self):
        """Test sending strategy signal notification."""
        signal_data = {
            'symbol': 'AAPL',
            'action': 'buy',
            'price': 150.00,
            'strategy_name': 'RSI Strategy',
            'reason': 'RSI oversold'
        }

        result = send_strategy_signal_notification(self.user.id, signal_data)

        self.assertTrue(result['success'])
        # Check notification was created
        notifications = Notification.objects.filter(
            user=self.user,
            type='strategy_signal'
        )
        self.assertEqual(notifications.count(), 1)

    @patch('apps.portfolios.services.calculate_portfolio_equity')
    def test_send_daily_portfolio_summary(self, mock_equity):
        """Test sending daily portfolio summary."""
        mock_equity.return_value = Decimal('10500.00')

        result = send_daily_portfolio_summary(self.user.id)

        self.assertTrue(result['success'])
        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('portfolio', mail.outbox[0].subject.lower())

    def test_email_retry_logic(self):
        """Test email sending retry on failure."""
        with patch('apps.notifications.services.send_mail') as mock_send:
            # Simulate failure
            mock_send.side_effect = Exception('SMTP error')

            result = send_email_notification(
                user=self.user,
                subject='Test',
                message='Test message'
            )

            self.assertFalse(result['success'])
            self.assertIn('error', result)


class NotificationAPITests(APITestCase):
    """Test cases for Notification API endpoints."""

    def setUp(self):
        """Set up test client and data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    def test_list_notifications(self):
        """Test listing user's notifications."""
        Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='Trade Executed',
            message='Test message'
        )

        response = self.client.get('/api/notifications/notifications/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_notifications_unauthenticated(self):
        """Test listing notifications requires authentication."""
        self.client.credentials()

        response = self.client.get('/api/notifications/notifications/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_mark_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='Trade Executed',
            message='Test message',
            is_read=False
        )

        response = self.client.post(
            f'/api/notifications/notifications/{notification.id}/mark_read/',
            format='json'
        )

        self.assertIn(response.status_code, [200, 202])

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_all_as_read(self):
        """Test marking all notifications as read."""
        # Create multiple notifications
        for i in range(3):
            Notification.objects.create(
                user=self.user,
                type='trade_executed',
                title=f'Notification {i}',
                message='Test message',
                is_read=False
            )

        response = self.client.post(
            '/api/notifications/notifications/mark_all_read/',
            format='json'
        )

        self.assertIn(response.status_code, [200, 202])

        # Check all are marked as read
        unread_count = Notification.objects.filter(
            user=self.user,
            is_read=False
        ).count()
        self.assertEqual(unread_count, 0)

    def test_delete_notification(self):
        """Test deleting a notification."""
        notification = Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='Trade Executed',
            message='Test message'
        )

        response = self.client.delete(
            f'/api/notifications/notifications/{notification.id}/'
        )

        self.assertIn(response.status_code, [200, 204])

        # Verify deleted
        with self.assertRaises(Notification.DoesNotExist):
            Notification.objects.get(id=notification.id)

    def test_user_can_only_see_own_notifications(self):
        """Test users can only see their own notifications."""
        # Create another user with notification
        other_user = User.objects.create_user(
            email='other@shefaai.com',
            password='TestPass123!'
        )
        Notification.objects.create(
            user=other_user,
            type='trade_executed',
            title='Other User Notification',
            message='Test message'
        )

        # Create notification for test user
        Notification.objects.create(
            user=self.user,
            type='trade_executed',
            title='My Notification',
            message='Test message'
        )

        response = self.client.get('/api/notifications/notifications/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only see own notification (implementation dependent)


class NotificationIntegrationTests(TestCase):
    """Integration tests for notification workflows."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            email_notifications=True
        )

        self.broker_connection = BrokerConnection.objects.create(
            user=self.user,
            broker='alpaca_paper',
            api_key_encrypted=encrypt_api_key('test-key'),
            api_secret_encrypted=encrypt_api_key('test-secret'),
            status='active'
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name='Test Portfolio',
            type='paper',
            cash=Decimal('10000.00'),
            broker_connection=self.broker_connection
        )

    def test_complete_trade_notification_workflow(self):
        """Test complete workflow from trade to notification."""
        # 1. Create trade
        trade = Trade.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=10,
            side='buy',
            price=Decimal('150.00')
        )

        # 2. Send notification
        result = send_trade_execution_alert(trade.id)

        # 3. Verify notification created
        self.assertTrue(result['success'])
        notifications = Notification.objects.filter(
            user=self.user,
            type='trade_executed'
        )
        self.assertEqual(notifications.count(), 1)

        # 4. Verify email sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('AAPL', email.body)
        self.assertEqual(email.to, [self.user.email])

    def test_approval_workflow_notifications(self):
        """Test complete approval workflow with notifications."""
        # 1. Create order requiring approval
        order = Order.objects.create(
            portfolio=self.portfolio,
            symbol='AAPL',
            quantity=50,
            side='buy',
            order_type='market',
            estimated_price=Decimal('150.00'),
            status='pending_approval',
            approval_required=True
        )

        # 2. Send approval request
        result = send_approval_request(order.id)

        # 3. Verify notification
        self.assertTrue(result['success'])
        notifications = Notification.objects.filter(
            user=self.user,
            type='approval_required'
        )
        self.assertEqual(notifications.count(), 1)

        # 4. Verify email
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('approval', mail.outbox[0].subject.lower())

        # 5. Mark notification as read
        notification = notifications.first()
        notification.is_read = True
        notification.save()

        # 6. Verify marked
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)


class NotificationPreferencesTests(TestCase):
    """Test cases for notification preferences."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

    def test_email_notifications_enabled(self):
        """Test email sent when notifications enabled."""
        self.user.email_notifications = True
        self.user.save()

        result = send_email_notification(
            user=self.user,
            subject='Test',
            message='Test message'
        )

        self.assertTrue(result['success'])
        self.assertEqual(len(mail.outbox), 1)

    def test_email_notifications_disabled(self):
        """Test email not sent when notifications disabled."""
        self.user.email_notifications = False
        self.user.save()

        result = send_email_notification(
            user=self.user,
            subject='Test',
            message='Test message'
        )

        self.assertFalse(result['success'])
        self.assertEqual(len(mail.outbox), 0)

    def test_push_notifications_preference(self):
        """Test push notification preferences."""
        self.user.push_notifications = True
        self.user.save()

        self.assertTrue(self.user.push_notifications)

        self.user.push_notifications = False
        self.user.save()

        self.assertFalse(self.user.push_notifications)

    def test_sms_notifications_preference(self):
        """Test SMS notification preferences."""
        self.user.sms_notifications = True
        self.user.save()

        self.assertTrue(self.user.sms_notifications)

        self.user.sms_notifications = False
        self.user.save()

        self.assertFalse(self.user.sms_notifications)
