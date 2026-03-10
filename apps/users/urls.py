"""
Authentication URLs for ShefaFx Trading Platform.
"""
from django.urls import path, include
from . import views

urlpatterns = [
    # Django REST Auth
    path('', include('dj_rest_auth.urls')),
    path('registration/', include('dj_rest_auth.registration.urls')),

    # Google OAuth
    path('google/', views.GoogleLogin.as_view(), name='google_login'),

    # User Profile
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/update/', views.update_profile, name='update_profile'),

    # Account Management
    path('delete-account/', views.delete_account, name='delete_account'),
    path('active-sessions/', views.active_sessions, name='active_sessions'),
    path('revoke-session/', views.revoke_session, name='revoke_session'),
]
