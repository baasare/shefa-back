"""
Authentication URLs for ShefaFx Trading Platform.
"""
from django.urls import path, include
from . import views, auth_views

urlpatterns = [
    path('login/', auth_views.EmailLoginView.as_view(), name='rest_login'),
    path('registration/', auth_views.RegistrationView.as_view(), name='rest_register'),
    path('registration/verify-email/', auth_views.ConfirmEmailView.as_view(), name='rest_verify_email'),
    path('registration/resend-email/', auth_views.ResendVerificationView.as_view(), name='rest_resend_email'),
    path('password/reset/', auth_views.ResetPasswordView.as_view(), name='rest_password_reset'),
    path('password/reset/confirm/', auth_views.ResetPasswordConfirmView.as_view(), name='rest_password_reset_confirm'),
    path('google/start/', auth_views.GoogleStartView.as_view(), name='google_start'),
    # Django REST Auth
    path('', include('dj_rest_auth.urls')),
    path('registration/', include('dj_rest_auth.registration.urls')),

    # Google OAuth
    path('google/', auth_views.GoogleLoginView.as_view(), name='google_login'),

    # User Profile
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/update/', views.update_profile, name='update_profile'),

    # Account Management
    path('delete-account/', views.delete_account, name='delete_account'),
    path('active-sessions/', views.active_sessions, name='active_sessions'),
    path('revoke-session/', views.revoke_session, name='revoke_session'),
]
