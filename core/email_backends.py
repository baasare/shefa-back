"""
Custom Django email backend using Resend.

This backend integrates Resend with Django's email system,
allowing django-allauth and other Django apps to use Resend for email delivery.
"""
import logging
from typing import List
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage, EmailMultiAlternatives
import resend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """
    Custom Django email backend that sends emails via Resend API.

    This backend allows Django's email system (including django-allauth)
    to send emails through Resend instead of SMTP.

    Usage:
        Set EMAIL_BACKEND in settings.py:
        EMAIL_BACKEND = 'core.email_backends.ResendEmailBackend'
    """

    def __init__(self, fail_silently=False, **kwargs):
        """
        Initialize the Resend backend.

        Args:
            fail_silently: If True, suppress exceptions during email sending
            **kwargs: Additional keyword arguments
        """
        super().__init__(fail_silently=fail_silently, **kwargs)

        # Get Resend configuration from settings
        self.api_key = getattr(settings, 'RESEND_API_KEY', None)
        self.from_email = getattr(settings, 'RESEND_FROM_EMAIL', 'noreply@shefaai.com')
        self.from_name = getattr(settings, 'RESEND_FROM_NAME', 'ShefaFx Trading')

        if not self.api_key:
            if not fail_silently:
                raise ValueError("RESEND_API_KEY is not configured in settings")
            logger.warning("RESEND_API_KEY not configured. Email sending will fail.")
        else:
            resend.api_key = self.api_key

    def send_messages(self, email_messages: List[EmailMessage]) -> int:
        """
        Send one or more EmailMessage objects and return the number of sent messages.

        Args:
            email_messages: List of Django EmailMessage objects to send

        Returns:
            Number of successfully sent emails
        """
        if not email_messages:
            return 0

        if not self.api_key:
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is not configured")
            logger.error("Cannot send emails: RESEND_API_KEY not configured")
            return 0

        num_sent = 0

        for message in email_messages:
            try:
                sent = self._send_message(message)
                if sent:
                    num_sent += 1
            except Exception as e:
                if not self.fail_silently:
                    raise
                logger.error(f"Error sending email via Resend: {e}")

        return num_sent

    def _send_message(self, message: EmailMessage) -> bool:
        """
        Send a single email message via Resend.

        Args:
            message: Django EmailMessage object

        Returns:
            True if sent successfully, False otherwise
        """
        # Extract recipients
        if not message.to:
            logger.warning("Email message has no recipients")
            return False

        # Prepare from address
        from_email = message.from_email or f"{self.from_name} <{self.from_email}>"

        # If from_email doesn't include name, add it
        if '<' not in from_email:
            from_email = f"{self.from_name} <{from_email}>"

        # Build email parameters
        params = {
            "from": from_email,
            "to": message.to,
            "subject": message.subject,
        }

        # Add CC and BCC if present
        if message.cc:
            params["cc"] = message.cc
        if message.bcc:
            params["bcc"] = message.bcc

        # Add reply-to if present
        if message.reply_to:
            params["reply_to"] = message.reply_to[0] if message.reply_to else None

        # Handle HTML and text content
        if isinstance(message, EmailMultiAlternatives):
            # EmailMultiAlternatives can have both HTML and text
            # Text body is in message.body
            params["text"] = message.body

            # HTML is in alternatives
            for content, mimetype in message.alternatives:
                if mimetype == 'text/html':
                    params["html"] = content
                    break
        else:
            # Regular EmailMessage - check if body is HTML
            if message.content_subtype == 'html':
                params["html"] = message.body
                # Generate plain text version (basic HTML stripping)
                import re
                params["text"] = re.sub('<[^<]+?>', '', message.body)
            else:
                params["text"] = message.body

        # Add tags for categorization
        tags = []

        # Detect email type from subject or content
        subject_lower = message.subject.lower()
        if 'verification' in subject_lower or 'confirm' in subject_lower:
            tags.append({"name": "type", "value": "email_verification"})
        elif 'password' in subject_lower and 'reset' in subject_lower:
            tags.append({"name": "type", "value": "password_reset"})
        elif 'welcome' in subject_lower:
            tags.append({"name": "type", "value": "welcome"})
        else:
            tags.append({"name": "type", "value": "auth"})

        tags.append({"name": "source", "value": "django-allauth"})

        if tags:
            params["tags"] = tags

        # Add custom headers if present
        if message.extra_headers:
            params["headers"] = message.extra_headers

        try:
            # Send via Resend
            response = resend.Emails.send(params)

            email_id = response.get('id', 'unknown')
            logger.info(
                f"Email sent via Resend: {email_id} | "
                f"To: {', '.join(message.to)} | "
                f"Subject: {message.subject}"
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to send email via Resend | "
                f"To: {', '.join(message.to)} | "
                f"Subject: {message.subject} | "
                f"Error: {e}"
            )
            if not self.fail_silently:
                raise
            return False

    def open(self):
        """
        Open a connection (not needed for API-based backend).
        """
        pass

    def close(self):
        """
        Close connection (not needed for API-based backend).
        """
        pass
