"""
Comprehensive test suite for the users app.
Tests authentication, user management, profiles, and all API endpoints.
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from decimal import Decimal
import json

from .models import User, UserProfile
from .serializers import UserSerializer, UserProfileSerializer, UserCreateSerializer

User = get_user_model()


def verify_email_automatically(email):
    """Automatically verify email in the database"""
    try:
        from allauth.account.models import EmailAddress
        EmailAddress.objects.filter(email=email).update(verified=True)
        print(f"✅ Email {email} automatically verified in database!")
        return True
    except Exception as e:
        print(f"❌ Failed to auto-verify email: {e}")
        return False


class UserModelTests(TestCase):
    """Test cases for the User model."""

    def setUp(self):
        """Set up test data."""
        self.user_data = {
            'email': 'testuser@shefaai.com',
            'password': 'TestPass123!',
            'first_name': 'Test',
            'last_name': 'User',
        }

    def test_create_user(self):
        """Test creating a regular user."""
        user = User.objects.create_user(**self.user_data)

        self.assertEqual(user.email, self.user_data['email'])
        self.assertEqual(user.first_name, self.user_data['first_name'])
        self.assertEqual(user.last_name, self.user_data['last_name'])
        self.assertTrue(user.check_password(self.user_data['password']))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_without_email(self):
        """Test that creating user without email raises ValueError."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email='', password='TestPass123!')

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email='admin@shefaai.com',
            password='AdminPass123!'
        )

        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_email_normalization(self):
        """Test that email is normalized."""
        email = 'test@SHEFAAI.COM'
        user = User.objects.create_user(email=email, password='TestPass123!')
        self.assertEqual(user.email, email.lower())

    def test_get_full_name(self):
        """Test get_full_name method."""
        user = User.objects.create_user(**self.user_data)
        expected_name = f"{self.user_data['first_name']} {self.user_data['last_name']}"
        self.assertEqual(user.get_full_name(), expected_name)

    def test_get_full_name_empty(self):
        """Test get_full_name returns email when name is empty."""
        user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )
        self.assertEqual(user.get_full_name(), user.email)

    def test_get_short_name(self):
        """Test get_short_name method."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.get_short_name(), self.user_data['first_name'])

    def test_get_short_name_no_first_name(self):
        """Test get_short_name when first_name is empty."""
        user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )
        self.assertEqual(user.get_short_name(), 'test')

    def test_display_name_property(self):
        """Test display_name property."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.display_name, user.get_full_name())

    def test_user_string_representation(self):
        """Test __str__ method returns email."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(str(user), user.email)

    def test_default_values(self):
        """Test default field values."""
        user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.assertEqual(user.risk_tolerance, 'moderate')
        self.assertEqual(user.experience_level, 'beginner')
        self.assertFalse(user.mfa_enabled)
        self.assertEqual(user.approval_threshold, Decimal('500.00'))
        self.assertTrue(user.email_notifications)
        self.assertTrue(user.push_notifications)
        self.assertFalse(user.sms_notifications)
        self.assertFalse(user.is_verified)


class UserProfileModelTests(TestCase):
    """Test cases for the UserProfile model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )
        self.profile = UserProfile.objects.create(user=self.user)

    def test_profile_creation(self):
        """Test profile can be created."""
        self.assertEqual(self.profile.user, self.user)
        self.assertIsNotNone(self.profile.created_at)
        self.assertIsNotNone(self.profile.updated_at)

    def test_profile_default_values(self):
        """Test default field values."""
        self.assertEqual(self.profile.timezone, 'US/Eastern')
        self.assertTrue(self.profile.default_paper_trading)
        self.assertEqual(self.profile.max_daily_loss_pct, Decimal('5.00'))
        self.assertEqual(self.profile.max_position_size_pct, Decimal('10.00'))

    def test_profile_string_representation(self):
        """Test __str__ method."""
        expected = f'{self.user.email} Profile'
        self.assertEqual(str(self.profile), expected)

    def test_profile_one_to_one_relationship(self):
        """Test one-to-one relationship with User."""
        self.assertEqual(self.user.profile, self.profile)

    def test_profile_cascade_delete(self):
        """Test profile is deleted when user is deleted."""
        user_id = self.user.id
        self.user.delete()

        with self.assertRaises(UserProfile.DoesNotExist):
            UserProfile.objects.get(user_id=user_id)


class UserSerializerTests(TestCase):
    """Test cases for user serializers."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            first_name='Test',
            last_name='User'
        )
        self.profile = UserProfile.objects.create(user=self.user)

    def test_user_serializer(self):
        """Test UserSerializer contains expected fields."""
        serializer = UserSerializer(self.user)
        data = serializer.data

        self.assertEqual(set(data.keys()), {
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'phone_number', 'risk_tolerance', 'experience_level',
            'mfa_enabled', 'approval_threshold',
            'email_notifications', 'push_notifications', 'sms_notifications',
            'is_active', 'is_verified', 'created_at', 'updated_at', 'profile'
        })

    def test_user_serializer_full_name(self):
        """Test full_name field in serializer."""
        serializer = UserSerializer(self.user)
        self.assertEqual(serializer.data['full_name'], 'Test User')

    def test_user_profile_serializer(self):
        """Test UserProfileSerializer contains expected fields."""
        serializer = UserProfileSerializer(self.profile)
        data = serializer.data

        self.assertIn('investment_goals', data)
        self.assertIn('timezone', data)
        self.assertIn('max_daily_loss_pct', data)

    def test_user_create_serializer_valid(self):
        """Test UserCreateSerializer with valid data."""
        data = {
            'email': 'newuser@shefaai.com',
            'password': 'NewPass123!',
            'password_confirm': 'NewPass123!',
            'first_name': 'New',
            'last_name': 'User'
        }

        serializer = UserCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_user_create_serializer_password_mismatch(self):
        """Test UserCreateSerializer fails on password mismatch."""
        data = {
            'email': 'newuser@shefaai.com',
            'password': 'NewPass123!',
            'password_confirm': 'DifferentPass123!',
            'first_name': 'New',
            'last_name': 'User'
        }

        serializer = UserCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)

    def test_user_create_serializer_creates_profile(self):
        """Test that UserCreateSerializer creates profile."""
        data = {
            'email': 'newuser@shefaai.com',
            'password': 'NewPass123!',
            'password_confirm': 'NewPass123!',
            'first_name': 'New',
            'last_name': 'User'
        }

        serializer = UserCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()

        self.assertTrue(hasattr(user, 'profile'))
        self.assertIsInstance(user.profile, UserProfile)


class AuthenticationAPITests(APITestCase):
    """Test cases for authentication API endpoints."""

    def setUp(self):
        """Set up test data and client."""
        self.client = APIClient()
        self.registration_url = reverse('rest_register')
        self.login_url = reverse('rest_login')
        self.logout_url = reverse('rest_logout')

        self.user_data = {
            'email': 'testuser@shefaai.com',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!',
            'first_name': 'Test',
            'last_name': 'User'
        }

    @override_settings(
        ACCOUNT_EMAIL_VERIFICATION='none',
        ACCOUNT_EMAIL_REQUIRED=True
    )
    def test_user_registration_success(self):
        """Test successful user registration."""
        response = self.client.post(
            self.registration_url,
            self.user_data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)

        # Verify user was created
        user = User.objects.get(email=self.user_data['email'])
        self.assertEqual(user.first_name, self.user_data['first_name'])
        self.assertEqual(user.last_name, self.user_data['last_name'])

    def test_user_registration_invalid_email(self):
        """Test registration with invalid email."""
        data = self.user_data.copy()
        data['email'] = 'invalid-email'

        response = self.client.post(self.registration_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_registration_password_mismatch(self):
        """Test registration with mismatched passwords."""
        data = self.user_data.copy()
        data['password2'] = 'DifferentPass123!'

        response = self.client.post(self.registration_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_registration_duplicate_email(self):
        """Test registration with duplicate email."""
        User.objects.create_user(
            email=self.user_data['email'],
            password='SomePass123!'
        )

        response = self.client.post(
            self.registration_url,
            self.user_data,
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_login_success(self):
        """Test successful user login."""
        # Create and verify user
        user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        # Verify email to allow login
        verify_email_automatically('test@shefaai.com')

        login_data = {
            'email': 'test@shefaai.com',
            'password': 'TestPass123!'
        }

        response = self.client.post(self.login_url, login_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)

    def test_user_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        # Verify email to allow login attempt
        verify_email_automatically('test@shefaai.com')

        login_data = {
            'email': 'test@shefaai.com',
            'password': 'WrongPassword!'
        }

        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_login_nonexistent_user(self):
        """Test login with non-existent user."""
        login_data = {
            'email': 'nonexistent@shefaai.com',
            'password': 'TestPass123!'
        }

        response = self.client.post(self.login_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_login_unverified_email(self):
        """Test login with unverified email fails."""
        # Create user without verifying email
        User.objects.create_user(
            email='unverified@shefaai.com',
            password='TestPass123!'
        )

        login_data = {
            'email': 'unverified@shefaai.com',
            'password': 'TestPass123!'
        }

        response = self.client.post(self.login_url, login_data, format='json')
        # Should fail because email is not verified
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_user_logout(self):
        """Test user logout."""
        user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        response = self.client.post(self.logout_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class UserProfileAPITests(APITestCase):
    """Test cases for user profile API endpoints."""

    def setUp(self):
        """Set up test data and authenticated client."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!',
            first_name='Test',
            last_name='User'
        )
        self.profile = UserProfile.objects.create(user=self.user)

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        self.profile_url = reverse('user_profile')
        self.update_profile_url = reverse('update_profile')

    def test_get_user_profile_authenticated(self):
        """Test retrieving user profile when authenticated."""
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['first_name'], self.user.first_name)
        self.assertIn('profile', response.data)

    def test_get_user_profile_unauthenticated(self):
        """Test retrieving user profile when not authenticated."""
        self.client.credentials()  # Clear credentials
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_user_profile_success(self):
        """Test updating user profile successfully."""
        update_data = {
            'first_name': 'Updated',
            'last_name': 'Name',
            'phone_number': '+1234567890',
            'risk_tolerance': 'aggressive'
        }

        response = self.client.patch(
            self.update_profile_url,
            update_data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], 'Updated')
        self.assertEqual(response.data['last_name'], 'Name')
        self.assertEqual(response.data['phone_number'], '+1234567890')
        self.assertEqual(response.data['risk_tolerance'], 'aggressive')

        # Verify database update
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')

    def test_update_user_profile_partial(self):
        """Test partial update of user profile."""
        update_data = {'first_name': 'NewFirst'}

        response = self.client.patch(
            self.update_profile_url,
            update_data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], 'NewFirst')
        self.assertEqual(response.data['last_name'], self.user.last_name)

    def test_update_user_profile_invalid_data(self):
        """Test updating profile with invalid data."""
        update_data = {
            'risk_tolerance': 'invalid_value'
        }

        response = self.client.patch(
            self.update_profile_url,
            update_data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_user_profile_unauthenticated(self):
        """Test updating profile when not authenticated."""
        self.client.credentials()  # Clear credentials
        update_data = {'first_name': 'Updated'}

        response = self.client.patch(
            self.update_profile_url,
            update_data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_user_profile_readonly_fields(self):
        """Test that readonly fields cannot be updated."""
        original_email = self.user.email
        update_data = {
            'email': 'newemail@shefaai.com',
            'is_verified': True
        }

        response = self.client.patch(
            self.update_profile_url,
            update_data,
            format='json'
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, original_email)
        self.assertFalse(self.user.is_verified)


class JWTTokenTests(APITestCase):
    """Test cases for JWT token functionality."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )

        self.client = APIClient()
        self.token_refresh_url = reverse('token_refresh')
        self.token_verify_url = reverse('token_verify')

    def test_token_refresh(self):
        """Test refreshing access token."""
        refresh = RefreshToken.for_user(self.user)

        response = self.client.post(
            self.token_refresh_url,
            {'refresh': str(refresh)},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_token_refresh_invalid(self):
        """Test refreshing with invalid token."""
        response = self.client.post(
            self.token_refresh_url,
            {'refresh': 'invalid_token'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_verify_valid(self):
        """Test verifying valid token."""
        refresh = RefreshToken.for_user(self.user)
        access_token = str(refresh.access_token)

        response = self.client.post(
            self.token_verify_url,
            {'token': access_token},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_token_verify_invalid(self):
        """Test verifying invalid token."""
        response = self.client.post(
            self.token_verify_url,
            {'token': 'invalid_token'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_access_protected_endpoint_with_valid_token(self):
        """Test accessing protected endpoint with valid token."""
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        response = self.client.get(reverse('user_profile'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_access_protected_endpoint_without_token(self):
        """Test accessing protected endpoint without token."""
        response = self.client.get(reverse('user_profile'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordManagementTests(APITestCase):
    """Test cases for password management."""

    def setUp(self):
        """Set up test user and client."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='OldPass123!'
        )

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        self.password_change_url = reverse('rest_password_change')

    def test_password_change_success(self):
        """Test successful password change."""
        data = {
            'old_password': 'OldPass123!',
            'new_password1': 'NewPass123!',
            'new_password2': 'NewPass123!'
        }

        response = self.client.post(
            self.password_change_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify password was changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass123!'))

    def test_password_change_wrong_old_password(self):
        """Test password change with wrong old password."""
        data = {
            'old_password': 'WrongPass123!',
            'new_password1': 'NewPass123!',
            'new_password2': 'NewPass123!'
        }

        response = self.client.post(
            self.password_change_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_change_mismatch(self):
        """Test password change with mismatched new passwords."""
        data = {
            'old_password': 'OldPass123!',
            'new_password1': 'NewPass123!',
            'new_password2': 'DifferentPass123!'
        }

        response = self.client.post(
            self.password_change_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_change_unauthenticated(self):
        """Test password change when not authenticated."""
        self.client.credentials()  # Clear credentials

        data = {
            'old_password': 'OldPass123!',
            'new_password1': 'NewPass123!',
            'new_password2': 'NewPass123!'
        }

        response = self.client.post(
            self.password_change_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserPreferencesTests(APITestCase):
    """Test cases for user preferences and settings."""

    def setUp(self):
        """Set up test user with profile."""
        self.user = User.objects.create_user(
            email='test@shefaai.com',
            password='TestPass123!'
        )
        self.profile = UserProfile.objects.create(user=self.user)

        self.client = APIClient()
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        self.update_profile_url = reverse('update_profile')

    def test_update_risk_tolerance(self):
        """Test updating risk tolerance."""
        data = {'risk_tolerance': 'conservative'}

        response = self.client.patch(
            self.update_profile_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.risk_tolerance, 'conservative')

    def test_update_experience_level(self):
        """Test updating experience level."""
        data = {'experience_level': 'expert'}

        response = self.client.patch(
            self.update_profile_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.experience_level, 'expert')

    def test_update_notification_settings(self):
        """Test updating notification preferences."""
        data = {
            'email_notifications': False,
            'push_notifications': False,
            'sms_notifications': True
        }

        response = self.client.patch(
            self.update_profile_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_notifications)
        self.assertFalse(self.user.push_notifications)
        self.assertTrue(self.user.sms_notifications)

    def test_update_approval_threshold(self):
        """Test updating trade approval threshold."""
        data = {'approval_threshold': '1000.00'}

        response = self.client.patch(
            self.update_profile_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.approval_threshold, Decimal('1000.00'))

    def test_update_multiple_preferences(self):
        """Test updating multiple preferences at once."""
        data = {
            'risk_tolerance': 'aggressive',
            'experience_level': 'advanced',
            'approval_threshold': '2000.00',
            'email_notifications': False
        }

        response = self.client.patch(
            self.update_profile_url,
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.risk_tolerance, 'aggressive')
        self.assertEqual(self.user.experience_level, 'advanced')
        self.assertEqual(self.user.approval_threshold, Decimal('2000.00'))
        self.assertFalse(self.user.email_notifications)


class GoogleOAuthTests(APITestCase):
    """Test cases for Google OAuth login."""

    def setUp(self):
        """Set up client."""
        self.client = APIClient()
        self.google_login_url = reverse('google_login')

    def test_google_login_endpoint_exists(self):
        """Test that Google login endpoint exists."""
        # This will return 400 without valid OAuth data, but confirms endpoint exists
        response = self.client.post(self.google_login_url, {}, format='json')
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_405_METHOD_NOT_ALLOWED]
        )

    def test_google_login_requires_data(self):
        """Test that Google login requires OAuth data."""
        response = self.client.post(self.google_login_url, {}, format='json')
        # Should fail without proper OAuth tokens
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)


class UserQueryTests(TestCase):
    """Test cases for user queries and filtering."""

    def setUp(self):
        """Set up test users."""
        self.user1 = User.objects.create_user(
            email='user1@shefaai.com',
            password='Pass123!',
            risk_tolerance='conservative'
        )
        self.user2 = User.objects.create_user(
            email='user2@shefaai.com',
            password='Pass123!',
            risk_tolerance='aggressive'
        )
        self.user3 = User.objects.create_user(
            email='user3@shefaai.com',
            password='Pass123!',
            is_active=False
        )

    def test_filter_by_risk_tolerance(self):
        """Test filtering users by risk tolerance."""
        conservative_users = User.objects.filter(risk_tolerance='conservative')
        self.assertEqual(conservative_users.count(), 1)
        self.assertEqual(conservative_users.first(), self.user1)

    def test_filter_active_users(self):
        """Test filtering active users."""
        active_users = User.objects.filter(is_active=True)
        self.assertEqual(active_users.count(), 2)

    def test_filter_inactive_users(self):
        """Test filtering inactive users."""
        inactive_users = User.objects.filter(is_active=False)
        self.assertEqual(inactive_users.count(), 1)
        self.assertEqual(inactive_users.first(), self.user3)

    def test_user_ordering(self):
        """Test users are ordered by created_at descending."""
        users = User.objects.all()
        # User3 was created last, should be first
        self.assertEqual(users[0], self.user3)
