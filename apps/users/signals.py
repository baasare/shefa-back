"""
Signal handlers for user app.

Syncs email verification status between django-allauth and User model.
"""
from django.dispatch import receiver
from allauth.account.signals import email_confirmed
from apps.users.models import User


@receiver(email_confirmed)
def email_confirmed_handler(sender, request, email_address, **kwargs):
    """
    Sync email verification status from EmailAddress to User model.

    When django-allauth confirms an email, update the User.is_verified field.
    """
    user = email_address.user

    # Update user's is_verified field
    if not user.is_verified:
        user.is_verified = True
        user.save(update_fields=['is_verified'])

        print(f"✓ User {user.email} email verified and synced to User model")
