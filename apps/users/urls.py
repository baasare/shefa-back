"""
Authentication URLs for ShefaFx Trading Platform.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

urlpatterns = [
    # Django REST Auth
    path('auth/', include('dj_rest_auth.urls')),
    path('auth/registration/', include('dj_rest_auth.registration.urls')),

    # Google OAuth
    path('auth/google/', views.GoogleLogin.as_view(), name='google_login'),

    # User Profile
    path('auth/profile/', views.user_profile, name='user_profile'),
    path('auth/profile/update/', views.update_profile, name='update_profile'),

    # Router URLs
    path('', include(router.urls)),
]
