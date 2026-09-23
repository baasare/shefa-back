"""Public authentication endpoints with delivery and OAuth safeguards."""
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import RegisterView, SocialLoginView, ResendEmailVerificationView, VerifyEmailView
from dj_rest_auth.views import LoginView, PasswordResetView, PasswordResetConfirmView
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView


class AuthThrottle(AnonRateThrottle):
    rate = '20/min'


class PublicAuthMixin:
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AuthThrottle,)


class RegistrationView(PublicAuthMixin, RegisterView):
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # Roll back account creation if the provider cannot accept the email.
        return super().create(request, *args, **kwargs)


class EmailLoginView(PublicAuthMixin, LoginView):
    pass


class ResendVerificationView(PublicAuthMixin, ResendEmailVerificationView):
    pass


class ConfirmEmailView(PublicAuthMixin, VerifyEmailView):
    pass


class ResetPasswordView(PublicAuthMixin, PasswordResetView):
    pass


class ResetPasswordConfirmView(PublicAuthMixin, PasswordResetConfirmView):
    pass


class GoogleStartView(PublicAuthMixin, APIView):
    def get(self, request):
        app = settings.SOCIALACCOUNT_PROVIDERS['google']['APPS'][0]
        if not app['client_id'] or not app['secret']:
            error = APIException('Google sign-in is temporarily unavailable. Please sign in with email.')
            error.status_code = 503
            raise error
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        request.session['google_oauth'] = {'state': state, 'verifier': verifier, 'created': time.time()}
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        params = {
            'client_id': app['client_id'], 'redirect_uri': f"{settings.FRONTEND_URL.rstrip('/')}/callback",
            'response_type': 'code', 'scope': 'openid email profile', 'state': state,
            'code_challenge': challenge, 'code_challenge_method': 'S256', 'prompt': 'select_account',
        }
        return Response({'url': 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)})


class GooglePKCEClient(OAuth2Client):
    def get_access_token(self, code, pkce_code_verifier=None):
        return super().get_access_token(code, pkce_code_verifier=self.request.google_pkce_verifier)


class GoogleLoginView(PublicAuthMixin, SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = GooglePKCEClient

    @property
    def callback_url(self):
        return f"{settings.FRONTEND_URL.rstrip('/')}/callback"

    def post(self, request, *args, **kwargs):
        flow = request.session.get('google_oauth', {})
        state = request.data.get('state')
        if (not isinstance(state, str) or not state or
                not secrets.compare_digest(state, flow.get('state', '')) or
                time.time() - flow.get('created', 0) > 600):
            raise ValidationError({'detail': 'Your Google sign-in session expired. Please start again.'})
        request.session.pop('google_oauth', None)
        request._request.google_pkce_verifier = flow['verifier']
        if not request.data.get('code') or request.data.get('access_token') or request.data.get('id_token'):
            raise ValidationError({'detail': 'An authorization code is required.'})
        return super().post(request, *args, **kwargs)
