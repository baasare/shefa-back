"""
Custom django-allauth adapter for email customization.

Provides custom email templates and behavior for authentication emails.
"""
from django.conf import settings
from allauth.account.adapter import DefaultAccountAdapter


class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Custom account adapter for django-allauth.

    Customizes email sending behavior and templates.
    """

    def get_from_email(self):
        """
        Get the from email address for allauth emails.

        Returns:
            Formatted from email with name
        """
        from_email = getattr(settings, 'RESEND_FROM_EMAIL', 'noreply@shefaai.com')
        from_name = getattr(settings, 'RESEND_FROM_NAME', 'ShefaFx Trading')
        return f"{from_name} <{from_email}>"

    def send_mail(self, template_prefix, email, context):
        """
        Override send_mail to use custom formatting.

        Args:
            template_prefix: Template prefix for the email
            email: Recipient email address
            context: Template context dictionary
        """
        # Add custom context variables
        context['site_name'] = 'ShefaFx Trading Platform'
        context['site_url'] = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        context['support_email'] = 'support@shefaai.com'

        # Call parent implementation
        return super().send_mail(template_prefix, email, context)

    def get_email_confirmation_url(self, request, emailconfirmation):
        """
        Construct the email confirmation URL.

        Args:
            request: HTTP request object
            emailconfirmation: EmailConfirmation instance

        Returns:
            Confirmation URL pointing to frontend
        """
        # Point to frontend URL instead of backend
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        return f"{frontend_url}/verify-email/{emailconfirmation.key}"

    def get_password_reset_url(self, request, uid, token):
        """
        Construct the password reset URL.

        Args:
            request: HTTP request object
            uid: User ID
            token: Reset token

        Returns:
            Password reset URL pointing to frontend
        """
        # Point to frontend URL instead of backend
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        return f"{frontend_url}/reset-password/{uid}/{token}"
