"""
Custom authentication backends for ShefaFx Trading Platform.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class SoftDeleteAwareBackend(ModelBackend):
    """
    Authentication backend that properly handles soft-deleted users.

    This backend extends Django's ModelBackend to use the all_objects manager
    which includes soft-deleted users. This prevents DoesNotExist errors when
    JWT tokens try to refresh for users who have been soft-deleted.

    Soft-deleted users are still blocked from authentication because
    is_active is checked by default in the authentication flow.
    """

    def get_user(self, user_id):
        """
        Get user by ID, including soft-deleted users.
        This is needed for JWT token validation.
        """
        try:
            user = User.all_objects.get(pk=user_id)
            # Still check if the user should be allowed
            if user.is_deleted:
                # Return None so the token is invalid for deleted users
                return None
            return user
        except User.DoesNotExist:
            return None
