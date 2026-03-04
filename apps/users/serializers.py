"""
User serializers for ShefaFx Trading Platform.
"""
from rest_framework import serializers
from apps.users.models import User, UserProfile
from dj_rest_auth.registration.serializers import RegisterSerializer
from dj_rest_auth.serializers import JWTSerializer
from allauth.account.adapter import get_adapter
from django.db import transaction
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken
from django.contrib.auth import get_user_model


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
            'is_active', 'is_verified', 'created_at', 'updated_at',
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
    """
    first_name = serializers.CharField(required=False, max_length=150)
    last_name = serializers.CharField(required=False, max_length=150)

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
