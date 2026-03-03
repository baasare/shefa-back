"""
User models for ShefaFx Trading Platform.
"""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError('Users must have an email address')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom user model for trading platform with email authentication."""

    RISK_TOLERANCE_CHOICES = [
        ('conservative', 'Conservative'),
        ('moderate', 'Moderate'),
        ('aggressive', 'Aggressive'),
    ]

    EXPERIENCE_LEVEL_CHOICES = [
        ('beginner', 'Beginner (< 1 year)'),
        ('intermediate', 'Intermediate (1-3 years)'),
        ('advanced', 'Advanced (3-5 years)'),
        ('expert', 'Expert (5+ years)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)
    email = models.EmailField('Email Address', unique=True, db_index=True)

    # Profile Information
    first_name = models.CharField('First Name', max_length=150, blank=True)
    last_name = models.CharField('Last Name', max_length=150, blank=True)
    phone_number = models.CharField('Phone Number', max_length=20, blank=True)

    # Trading Preferences
    risk_tolerance = models.CharField(
        'Risk Tolerance',
        max_length=20,
        choices=RISK_TOLERANCE_CHOICES,
        default='moderate'
    )
    experience_level = models.CharField(
        'Trading Experience',
        max_length=20,
        choices=EXPERIENCE_LEVEL_CHOICES,
        default='beginner'
    )

    # Security
    mfa_enabled = models.BooleanField('2FA Enabled', default=False)
    mfa_secret = models.CharField('2FA Secret', max_length=32, blank=True)

    # Approval Thresholds (in USD)
    approval_threshold = models.DecimalField(
        'Trade Approval Threshold',
        max_digits=15,
        decimal_places=2,
        default=500.00,
        validators=[MinValueValidator(0)]
    )

    # Notifications
    email_notifications = models.BooleanField('Email Notifications', default=True)
    push_notifications = models.BooleanField('Push Notifications', default=True)
    sms_notifications = models.BooleanField('SMS Notifications', default=False)

    # Metadata
    is_active = models.BooleanField('Active', default=True)
    is_verified = models.BooleanField('Email Verified', default=False)
    created_at = models.DateTimeField('Date Joined', auto_now_add=True)
    updated_at = models.DateTimeField('Last Updated', auto_now=True)
    last_login_ip = models.GenericIPAddressField('Last Login IP', blank=True, null=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_active', 'is_verified']),
        ]

    def __str__(self):
        return self.email

    def get_full_name(self):
        """Return the user's full name."""
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name or self.email

    def get_short_name(self):
        """Return the user's first name or email."""
        return self.first_name or self.email.split('@')[0]

    @property
    def display_name(self):
        """Return a display-friendly name."""
        return self.get_full_name()


class UserProfile(models.Model):
    """Extended user profile information."""

    TIMEZONE_CHOICES = [
        ('US/Eastern', 'Eastern Time (ET)'),
        ('US/Central', 'Central Time (CT)'),
        ('US/Mountain', 'Mountain Time (MT)'),
        ('US/Pacific', 'Pacific Time (PT)'),
        ('Europe/London', 'London (GMT)'),
        ('UTC', 'UTC'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        primary_key=True
    )

    # Trading Goals
    investment_goals = models.TextField('Investment Goals', blank=True)
    time_horizon = models.CharField('Investment Time Horizon', max_length=100, blank=True)
    preferred_asset_classes = models.JSONField('Preferred Asset Classes', default=list, blank=True)

    # Settings
    timezone = models.CharField(
        'Timezone',
        max_length=50,
        choices=TIMEZONE_CHOICES,
        default='US/Eastern'
    )
    default_paper_trading = models.BooleanField('Default to Paper Trading', default=True)

    # Risk Parameters
    max_daily_loss_pct = models.DecimalField(
        'Max Daily Loss %',
        max_digits=5,
        decimal_places=2,
        default=5.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    max_position_size_pct = models.DecimalField(
        'Max Position Size %',
        max_digits=5,
        decimal_places=2,
        default=10.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    # Metadata
    avatar_url = models.URLField('Avatar URL', blank=True)
    bio = models.TextField('Bio', max_length=500, blank=True)

    created_at = models.DateTimeField('Created At', auto_now_add=True)
    updated_at = models.DateTimeField('Updated At', auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f'{self.user.email} Profile'
