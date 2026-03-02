"""
User serializers for ShefaAI Trading Platform.
"""
from rest_framework import serializers
from .models import User, UserProfile


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
    profile = UserProfileSerializer(read_only=True)
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


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
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
