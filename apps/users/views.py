"""
Authentication views for ShefaFx Trading Platform.
"""
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from config import settings
from django.contrib.sessions.models import Session
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from user_agents import parse




class GoogleLogin(SocialLoginView):
    """
    Google OAuth2 login view.
    Accepts 'code' from frontend OAuth flow and exchanges it for tokens.
    """
    adapter_class = GoogleOAuth2Adapter
    callback_url = f"{settings.FRONTEND_URL}/callback"
    client_class = OAuth2Client


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """Get current user profile."""
    from .serializers import UserSerializer

    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """Update user profile."""
    from .serializers import UserSerializer

    serializer = UserSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """Soft delete user account."""
    user = request.user

    # Soft delete the user
    user.is_deleted = True
    user.deleted_at = timezone.now()
    user.is_active = False
    user.save()

    # Clear all active sessions for this user
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    for session in sessions:
        session_data = session.get_decoded()
        if session_data.get('_auth_user_id') == str(user.id):
            session.delete()

    return Response(
        {'message': 'Account has been deleted successfully.'},
        status=status.HTTP_200_OK
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def active_sessions(request):
    """Get all active sessions for the current user."""
    user = request.user
    current_sessions = []

    # Get all non-expired sessions
    sessions = Session.objects.filter(expire_date__gte=timezone.now())

    for session in sessions:
        session_data = session.get_decoded()
        if session_data.get('_auth_user_id') == str(user.id):
            # Extract device, browser, and location info
            user_agent_string = session_data.get('user_agent', 'Unknown')
            ip_address = session_data.get('ip_address', 'Unknown')

            # Parse user agent
            user_agent = parse(user_agent_string)

            # Get location from IP (placeholder - you can integrate a GeoIP service)
            location = session_data.get('location', 'Unknown')

            current_sessions.append({
                'session_key': session.session_key[:10] + '...',  # Partial key for security
                'expire_date': session.expire_date,
                'is_current': session.session_key == request.session.session_key,
                'device': f"{user_agent.device.family}",
                'browser': f"{user_agent.browser.family} {user_agent.browser.version_string}",
                'os': f"{user_agent.os.family} {user_agent.os.version_string}",
                'location': location,
                'ip_address': ip_address
            })

    return Response({
        'active_sessions_count': len(current_sessions),
        'sessions': current_sessions
    }, status=status.HTTP_200_OK)
