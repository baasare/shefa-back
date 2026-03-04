"""
User serializers for ShefaFx Trading Platform.
"""
from rest_framework import serializers
from apps.users.models import User, UserProfile
from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import JWTSerializer, PasswordResetSerializer, PasswordResetConfirmSerializer
from allauth.account.adapter import get_adapter
from django.db import transaction
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.encoding import force_str
from uuid import UUID


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for UserProfile model."""

    class Meta:
        model = UserProfile
        fields = [
            'investment_goals', 'time_horizon', 'preferred_asset_classes',
            'timezone', 'default_paper_trading', 'max_daily_loss_pct',
            'max_position_size_pct', 'avatar_url', 'bio',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""
    profile = UserProfileSerializer(read_only=False, required=False)
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'phone_number', 'risk_tolerance', 'experience_level',
            'mfa_enabled', 'approval_threshold',
            'email_notifications', 'push_notifications', 'sms_notifications',
            'is_active', 'is_verified', 'onboarding_completed', 'created_at', 'updated_at',
            'profile'
        ]
        read_only_fields = ['id', 'email', 'created_at', 'updated_at', 'is_verified']

    def update(self, instance, validated_data):
        """Update user and nested profile data."""
        profile_data = validated_data.pop('profile', None)

        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update profile if provided
        if profile_data:
            profile, created = UserProfile.objects.get_or_create(user=instance)
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        return instance


class CustomRegisterSerializer(RegisterSerializer):
    """
    Custom registration serializer for dj-rest-auth.
    Extends the default RegisterSerializer to include first_name and last_name.
    Handles soft-deleted users trying to re-register.
    """
    first_name = serializers.CharField(required=False, max_length=150)
    last_name = serializers.CharField(required=False, max_length=150)

    def validate_email(self, email):
        """
        Check if a soft-deleted user exists with this email.
        If so, prevent registration and inform the user.
        """
        email = get_adapter().clean_email(email)

        # Check for soft-deleted users with this email
        deleted_user = User.all_objects.filter(
            email=email,
            is_deleted=True
        ).first()

        if deleted_user:
            raise serializers.ValidationError(
                "An account with this email was previously deleted. "
                "Please contact support to restore your account or use a different email address."
            )

        return email

    def get_cleaned_data(self):
        """
        Override to include first_name and last_name in cleaned data.
        """
        data = super().get_cleaned_data()
        data['first_name'] = self.validated_data.get('first_name', '')
        data['last_name'] = self.validated_data.get('last_name', '')
        return data

    @transaction.atomic
    def save(self, request):
        """
        Save user with first_name and last_name, and create UserProfile.
        """
        # Call parent save to handle allauth registration flow
        # This will create EmailAddress and EmailConfirmation
        user = super().save(request)

        # Create UserProfile for the user if it doesn't exist
        if not hasattr(user, 'profile'):
            UserProfile.objects.create(user=user)

        return user


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for user registration (legacy/alternative)."""
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['email', 'password', 'password_confirm', 'first_name', 'last_name']

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        # Create profile
        UserProfile.objects.create(user=user)
        return user


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Custom token refresh serializer that handles deleted users gracefully.
    """
    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except get_user_model().DoesNotExist:
            raise InvalidToken({
                'detail': 'User associated with this token no longer exists. Please log in again.',
                'code': 'user_not_found'
            })


class CustomPasswordResetSerializer(PasswordResetSerializer):
    """
    Custom password reset serializer that uses frontend URLs.
    """
    def get_email_options(self):
        """Override to use custom adapter which provides frontend URLs."""
        return {
            'email_template_name': 'account/email/password_reset_key_message.txt',
            'html_email_template_name': 'account/email/password_reset_key_message.html',
            'subject_template_name': 'account/email/password_reset_key_subject.txt',
            'extra_email_context': {
                'site_name': 'ShefaFx Trading Platform',
                'frontend_url': settings.FRONTEND_URL,
            }
        }

    def save(self):
        """
        Override save to use allauth adapter's password reset URL generation.
        This ensures the reset link points to the frontend.
        """
        request = self.context.get('request')
        opts = self.get_email_options()
        from allauth.account.forms import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes

        email = self.validated_data['email']
        User = get_user_model()

        # Get users with this email
        users = User.objects.filter(email__iexact=email, is_active=True)

        for user in users:
            # Generate token
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            # Get password reset URL from adapter
            adapter = get_adapter()
            url = adapter.get_password_reset_url(request, uid, token)

            # Send email via adapter
            context = {
                'user': user,
                'password_reset_url': url,
                'request': request,
                **opts.get('extra_email_context', {})
            }

            adapter.send_mail(
                'account/email/password_reset_key',
                email,
                context
            )


class CustomPasswordResetConfirmSerializer(PasswordResetConfirmSerializer):
    """
    Custom password reset confirm serializer that properly handles base64-encoded UIDs.
    Matches the encoding used in CustomPasswordResetSerializer.
    """
    # Override uid field to accept string instead of UUID
    uid = serializers.CharField()

    def validate(self, attrs):
        """
        Validate the token and decode the UID to get the user.
        Uses base64 decoding to match the encoding in CustomPasswordResetSerializer.
        Handles UUID primary keys by converting the decoded string to UUID.
        """
        from allauth.account.forms import default_token_generator
        from django.utils.http import urlsafe_base64_decode

        try:
            # Decode the base64-encoded UID
            uid_str = force_str(urlsafe_base64_decode(attrs['uid']))
            # Convert to UUID if the model uses UUID primary keys
            try:
                uid = UUID(uid_str)
            except ValueError:
                # If not a valid UUID, use the string directly (for integer PKs)
                uid = uid_str
            self.user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({'uid': ['Invalid value']})

        # Validate the token
        if not default_token_generator.check_token(self.user, attrs['token']):
            raise serializers.ValidationError({'token': ['Invalid or expired token']})

        # Set up the SetPasswordForm for password validation
        from django.contrib.auth.forms import SetPasswordForm
        self.set_password_form = SetPasswordForm(
            user=self.user,
            data={
                'new_password1': attrs['new_password1'],
                'new_password2': attrs['new_password2']
            }
        )

        if not self.set_password_form.is_valid():
            raise serializers.ValidationError(self.set_password_form.errors)

        return attrs

    def save(self):
        """Save the new password."""
        return self.set_password_form.save()
