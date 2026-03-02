"""
Email service using Resend SDK.

This module provides a wrapper around the Resend email service,
replacing Django's default email backend for more reliable transactional emails.
"""
import logging
from typing import Dict, Any, List, Optional
from django.conf import settings
import resend

logger = logging.getLogger(__name__)


class ResendEmailService:
    """
    Service for sending emails via Resend API.

    Provides a clean interface for sending various types of emails
    with proper error handling and logging.
    """

    def __init__(self):
        """Initialize Resend with API key from settings."""
        self.api_key = getattr(settings, 'RESEND_API_KEY', None)
        if not self.api_key:
            logger.warning("RESEND_API_KEY not configured. Email sending will fail.")
        else:
            resend.api_key = self.api_key

        self.from_email = getattr(settings, 'RESEND_FROM_EMAIL', 'noreply@shefaai.com')
        self.from_name = getattr(settings, 'RESEND_FROM_NAME', 'ShefaAI Trading')

    def send_email(
        self,
        to: List[str],
        subject: str,
        html: Optional[str] = None,
        text: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[Dict[str, str]]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Send an email via Resend.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            html: HTML content (optional)
            text: Plain text content (optional, defaults to html if not provided)
            reply_to: Reply-to email address (optional)
            tags: List of tags for categorization (optional)
            headers: Custom headers (optional)

        Returns:
            Dict with send result including 'success' and 'id' or 'error'

        Raises:
            Exception: If Resend API call fails
        """
        if not self.api_key:
            logger.error("Cannot send email: RESEND_API_KEY not configured")
            return {
                'success': False,
                'error': 'Email service not configured'
            }

        # Ensure we have either HTML or text content
        if not html and not text:
            logger.error("Cannot send email: No content provided")
            return {
                'success': False,
                'error': 'No email content provided'
            }

        # Default text to html if not provided
        if html and not text:
            # Strip HTML tags for plain text version (basic implementation)
            import re
            text = re.sub('<[^<]+?>', '', html)

        try:
            params = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": to,
                "subject": subject,
            }

            # Add optional parameters
            if html:
                params["html"] = html
            if text:
                params["text"] = text
            if reply_to:
                params["reply_to"] = reply_to
            if tags:
                params["tags"] = tags
            if headers:
                params["headers"] = headers

            # Send via Resend
            response = resend.Emails.send(params)

            logger.info(f"Email sent successfully via Resend: {response.get('id')}")

            return {
                'success': True,
                'id': response.get('id'),
                'response': response
            }

        except Exception as e:
            logger.error(f"Error sending email via Resend: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def send_notification_email(
        self,
        to_email: str,
        title: str,
        message: str,
        notification_type: str = 'info',
        action_url: Optional[str] = None,
        action_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a notification email with consistent formatting.

        Args:
            to_email: Recipient email address
            title: Email title/subject
            message: Notification message
            notification_type: Type of notification (info, success, warning, error)
            action_url: Optional URL for call-to-action button
            action_text: Optional text for call-to-action button

        Returns:
            Dict with send result
        """
        html = self._build_notification_html(
            title=title,
            message=message,
            notification_type=notification_type,
            action_url=action_url,
            action_text=action_text
        )

        return self.send_email(
            to=[to_email],
            subject=title,
            html=html,
            tags=[{"name": "type", "value": notification_type}]
        )

    def send_trade_execution_email(
        self,
        to_email: str,
        order_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send trade execution notification email.

        Args:
            to_email: Recipient email address
            order_data: Dictionary with order details

        Returns:
            Dict with send result
        """
        subject = f"Trade Executed: {order_data['side'].upper()} {order_data['symbol']}"

        html = self._build_trade_execution_html(order_data)

        return self.send_email(
            to=[to_email],
            subject=subject,
            html=html,
            tags=[
                {"name": "type", "value": "trade_execution"},
                {"name": "symbol", "value": order_data['symbol']}
            ]
        )

    def send_approval_request_email(
        self,
        to_email: str,
        order_data: Dict[str, Any],
        approval_url: str
    ) -> Dict[str, Any]:
        """
        Send order approval request email (HITL).

        Args:
            to_email: Recipient email address
            order_data: Dictionary with order details
            approval_url: URL to approve/reject the order

        Returns:
            Dict with send result
        """
        subject = f"Approval Required: {order_data['side'].upper()} {order_data['symbol']}"

        html = self._build_approval_request_html(order_data, approval_url)

        return self.send_email(
            to=[to_email],
            subject=subject,
            html=html,
            tags=[
                {"name": "type", "value": "approval_request"},
                {"name": "symbol", "value": order_data['symbol']}
            ]
        )

    def send_daily_summary_email(
        self,
        to_email: str,
        summary_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send daily portfolio summary email.

        Args:
            to_email: Recipient email address
            summary_data: Dictionary with portfolio summary data

        Returns:
            Dict with send result
        """
        subject = "Daily Portfolio Summary"

        html = self._build_daily_summary_html(summary_data)

        return self.send_email(
            to=[to_email],
            subject=subject,
            html=html,
            tags=[{"name": "type", "value": "daily_summary"}]
        )

    # HTML Template Builders

    def _build_notification_html(
        self,
        title: str,
        message: str,
        notification_type: str,
        action_url: Optional[str] = None,
        action_text: Optional[str] = None
    ) -> str:
        """Build HTML for notification email."""
        # Color scheme based on notification type
        colors = {
            'info': '#3b82f6',
            'success': '#10b981',
            'warning': '#f59e0b',
            'error': '#ef4444'
        }
        color = colors.get(notification_type, colors['info'])

        action_button = ""
        if action_url and action_text:
            action_button = f"""
            <div style="text-align: center; margin: 30px 0;">
                <a href="{action_url}"
                   style="background-color: {color}; color: white; padding: 12px 30px;
                          text-decoration: none; border-radius: 5px; display: inline-block;
                          font-weight: bold;">
                    {action_text}
                </a>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: {color}; color: white; padding: 20px; border-radius: 5px 5px 0 0;">
                <h1 style="margin: 0; font-size: 24px;">{title}</h1>
            </div>
            <div style="background-color: #f9fafb; padding: 30px; border-radius: 0 0 5px 5px;">
                <p style="font-size: 16px; margin: 0 0 20px 0;">{message}</p>
                {action_button}
                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="font-size: 12px; color: #6b7280; margin: 0;">
                    This is an automated notification from ShefaAI Trading Platform.<br>
                    If you have questions, please contact support.
                </p>
            </div>
        </body>
        </html>
        """

    def _build_trade_execution_html(self, order_data: Dict[str, Any]) -> str:
        """Build HTML for trade execution email."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #10b981; color: white; padding: 20px; border-radius: 5px 5px 0 0;">
                <h1 style="margin: 0; font-size: 24px;">✅ Trade Executed</h1>
            </div>
            <div style="background-color: #f9fafb; padding: 30px; border-radius: 0 0 5px 5px;">
                <p style="font-size: 16px;">Your trade has been successfully executed:</p>

                <table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
                    <tr style="background-color: #e5e7eb;">
                        <td style="padding: 10px; font-weight: bold;">Symbol</td>
                        <td style="padding: 10px;">{order_data.get('symbol', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; font-weight: bold;">Side</td>
                        <td style="padding: 10px; text-transform: uppercase;">{order_data.get('side', 'N/A')}</td>
                    </tr>
                    <tr style="background-color: #e5e7eb;">
                        <td style="padding: 10px; font-weight: bold;">Quantity</td>
                        <td style="padding: 10px;">{order_data.get('quantity', 'N/A')} shares</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; font-weight: bold;">Price</td>
                        <td style="padding: 10px;">${order_data.get('price', 0):.2f}</td>
                    </tr>
                    <tr style="background-color: #e5e7eb;">
                        <td style="padding: 10px; font-weight: bold;">Total Value</td>
                        <td style="padding: 10px; font-weight: bold;">${order_data.get('quantity', 0) * order_data.get('price', 0):,.2f}</td>
                    </tr>
                </table>

                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="font-size: 12px; color: #6b7280; margin: 0;">
                    ShefaAI Trading Platform<br>
                    This is an automated notification.
                </p>
            </div>
        </body>
        </html>
        """

    def _build_approval_request_html(self, order_data: Dict[str, Any], approval_url: str) -> str:
        """Build HTML for approval request email."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #f59e0b; color: white; padding: 20px; border-radius: 5px 5px 0 0;">
                <h1 style="margin: 0; font-size: 24px;">⏳ Approval Required</h1>
            </div>
            <div style="background-color: #f9fafb; padding: 30px; border-radius: 0 0 5px 5px;">
                <p style="font-size: 16px;">Your trading strategy wants to execute the following order:</p>

                <table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
                    <tr style="background-color: #e5e7eb;">
                        <td style="padding: 10px; font-weight: bold;">Symbol</td>
                        <td style="padding: 10px;">{order_data.get('symbol', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; font-weight: bold;">Action</td>
                        <td style="padding: 10px; text-transform: uppercase;">{order_data.get('side', 'N/A')}</td>
                    </tr>
                    <tr style="background-color: #e5e7eb;">
                        <td style="padding: 10px; font-weight: bold;">Quantity</td>
                        <td style="padding: 10px;">{order_data.get('quantity', 'N/A')} shares</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; font-weight: bold;">Estimated Cost</td>
                        <td style="padding: 10px; font-weight: bold;">${order_data.get('estimated_cost', 0):,.2f}</td>
                    </tr>
                </table>

                <div style="text-align: center; margin: 30px 0;">
                    <a href="{approval_url}"
                       style="background-color: #10b981; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; display: inline-block;
                              font-weight: bold; margin-right: 10px;">
                        ✓ Approve
                    </a>
                    <a href="{approval_url}"
                       style="background-color: #ef4444; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; display: inline-block;
                              font-weight: bold;">
                        ✗ Reject
                    </a>
                </div>

                <p style="font-size: 14px; color: #6b7280; background-color: #fef3c7; padding: 15px; border-radius: 5px;">
                    ⚠️ <strong>Please review and respond within 5 minutes.</strong><br>
                    This order will expire if not approved in time.
                </p>

                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="font-size: 12px; color: #6b7280; margin: 0;">
                    ShefaAI Trading Platform<br>
                    This is an automated notification.
                </p>
            </div>
        </body>
        </html>
        """

    def _build_daily_summary_html(self, summary_data: Dict[str, Any]) -> str:
        """Build HTML for daily summary email."""
        portfolios_html = ""
        for portfolio in summary_data.get('portfolios', []):
            portfolios_html += f"""
            <tr style="background-color: #f3f4f6;">
                <td style="padding: 10px;">{portfolio['name']}</td>
                <td style="padding: 10px; text-align: right;">${portfolio['value']:,.2f}</td>
                <td style="padding: 10px; text-align: right; color: {'#10b981' if portfolio.get('pnl', 0) >= 0 else '#ef4444'};">
                    ${portfolio.get('pnl', 0):,.2f}
                </td>
            </tr>
            """

        total_pnl = summary_data.get('total_pnl', 0)
        pnl_color = '#10b981' if total_pnl >= 0 else '#ef4444'

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #3b82f6; color: white; padding: 20px; border-radius: 5px 5px 0 0;">
                <h1 style="margin: 0; font-size: 24px;">📊 Daily Portfolio Summary</h1>
            </div>
            <div style="background-color: #f9fafb; padding: 30px; border-radius: 0 0 5px 5px;">
                <p style="font-size: 16px;">Here's your portfolio performance summary:</p>

                <table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
                    <thead>
                        <tr style="background-color: #e5e7eb;">
                            <th style="padding: 10px; text-align: left;">Portfolio</th>
                            <th style="padding: 10px; text-align: right;">Value</th>
                            <th style="padding: 10px; text-align: right;">P&L</th>
                        </tr>
                    </thead>
                    <tbody>
                        {portfolios_html}
                        <tr style="background-color: #dbeafe; font-weight: bold;">
                            <td style="padding: 10px;">Total</td>
                            <td style="padding: 10px; text-align: right;">${summary_data.get('total_value', 0):,.2f}</td>
                            <td style="padding: 10px; text-align: right; color: {pnl_color};">
                                ${total_pnl:,.2f}
                            </td>
                        </tr>
                    </tbody>
                </table>

                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                <p style="font-size: 12px; color: #6b7280; margin: 0;">
                    ShefaAI Trading Platform<br>
                    This is your daily automated summary.
                </p>
            </div>
        </body>
        </html>
        """


# Singleton instance
_email_service = None


def get_email_service() -> ResendEmailService:
    """Get or create email service singleton instance."""
    global _email_service
    if _email_service is None:
        _email_service = ResendEmailService()
    return _email_service
