"""
Signal handlers for user app.

Syncs email verification status between django-allauth and User model.
"""
from django.dispatch import receiver
from allauth.account.signals import email_confirmed
from allauth.socialaccount.signals import social_account_added
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


@receiver(social_account_added)
def social_account_added_handler(sender, request, sociallogin, **kwargs):
    """
    Mark user as verified when they sign in with a social account (Google, etc).

    Social providers like Google already verify emails, so we trust them.
    """
    user = sociallogin.user

    # Mark email as verified since social provider vouches for it
    if not user.is_verified:
        user.is_verified = True
        user.save(update_fields=['is_verified'])

        print(f"✓ User {user.email} verified via {sociallogin.account.provider} social login")
