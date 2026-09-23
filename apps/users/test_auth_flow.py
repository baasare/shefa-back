"""Regression coverage for production authentication contracts."""
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
import re
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.response import Response

@override_settings(ROOT_URLCONF='config.urls.api', DEFAULT_HOST='api', ALLOWED_HOSTS=['testserver'],
    FRONTEND_URL='https://shefafx.com', ACCOUNT_EMAIL_VERIFICATION='mandatory',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    MIDDLEWARE=[m for m in settings.MIDDLEWARE if not m.startswith('django_hosts.')])
class AuthFlowTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.payload = dict(email='auth-flow@example.com', password1='StrongPass984!', password2='StrongPass984!', first_name='Auth', last_name='Test')
    def post(self, path, data):
        return self.client.post('/v1/auth/' + path, data, format='json')
    def signup(self):
        return self.post('registration/', self.payload)
    def confirm(self):
        key = re.search(r'/confirm-email/([^\s<]+)', mail.outbox[-1].body).group(1)
        return self.post('registration/verify-email/', {'key': key})
    def test_signup_verification_login_refresh_logout(self):
        response = self.signup()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('access', response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('https://shefafx.com/confirm-email/', mail.outbox[0].body)
        self.assertIn('#0f1629', mail.outbox[0].alternatives[0][0])
        login = {'email': self.payload['email'], 'password': self.payload['password1']}
        self.assertEqual(self.post('login/', login).status_code, 400)
        self.assertEqual(self.confirm().status_code, 200)
        response = self.post('login/', login)
        self.assertEqual(response.status_code, 200, response.data)
        refresh = response.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
        self.assertEqual(self.client.get('/v1/auth/profile/').status_code, 200)
        self.client.credentials()
        renewed = self.post('token/refresh/', {'refresh': refresh})
        self.assertEqual(renewed.status_code, 200, renewed.data)
        self.assertIn('refresh', renewed.data)
        self.assertEqual(self.post('token/refresh/', {'refresh': refresh}).status_code, 401)
        self.assertEqual(self.post('logout/', {'refresh': renewed.data['refresh']}).status_code, 200)
        self.assertEqual(self.post('token/refresh/', {'refresh': renewed.data['refresh']}).status_code, 401)
    def test_duplicate_signup_is_validation_error(self):
        self.signup()
        response = self.signup()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(get_user_model().objects.filter(email=self.payload['email']).count(), 1)
    @override_settings(EMAIL_BACKEND='core.email_backends.ResendEmailBackend', RESEND_API_KEY='test-placeholder')
    @patch('core.email_backends.resend.Emails.send', side_effect=RuntimeError('provider unavailable'))
    def test_email_failure_rolls_back_signup(self, send):
        response = self.signup()
        self.assertEqual(response.status_code, 503, response.data)
        self.assertIn('try again', response.data['detail'])
        self.assertFalse(get_user_model().objects.filter(email=self.payload['email']).exists())
    def test_resend_recovers_existing_unverified_account(self):
        self.signup()
        self.assertEqual(self.post('registration/resend-email/', {'email': self.payload['email']}).status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.confirm().status_code, 200)
        self.assertEqual(self.post('registration/resend-email/', {'email': 'unknown@example.com'}).status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
    def test_password_reset_link_and_single_use(self):
        self.signup(); self.confirm()
        response = self.post('password/reset/', {'email': self.payload['email']})
        self.assertEqual(response.status_code, 200, response.data)
        uid, token = re.search(r'/reset-password/([^/\s]+)/([^\s<]+)', mail.outbox[-1].body).groups()
        data = dict(uid=uid, token=token, new_password1='AnotherStrong984!', new_password2='AnotherStrong984!')
        self.assertEqual(self.post('password/reset/confirm/', data).status_code, 200)
        self.assertEqual(self.post('password/reset/confirm/', data).status_code, 400)
        self.assertEqual(self.post('login/', {'email': self.payload['email'], 'password': 'AnotherStrong984!'}).status_code, 200)
    def test_invalid_verification_key(self):
        self.assertEqual(self.post('registration/verify-email/', {'key': 'invalid'}).status_code, 404)
    @override_settings(SOCIALACCOUNT_PROVIDERS={'google': {'APPS': [{'client_id': 'test-client', 'secret': 'test-secret', 'key': ''}]}})
    def test_google_state_pkce_and_replay_protection(self):
        response = self.client.get('/v1/auth/google/start/')
        self.assertEqual(response.status_code, 200)
        query = parse_qs(urlparse(response.data['url']).query)
        self.assertEqual(query['redirect_uri'], ['https://shefafx.com/callback'])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(self.post('google/', {'code': 'test-code', 'state': 'wrong'}).status_code, 400)
        with patch('dj_rest_auth.registration.views.SocialLoginView.post', return_value=Response({'ok': True})) as exchange:
            self.assertEqual(self.post('google/', {'code': 'test-code', 'state': query['state'][0]}).status_code, 200)
            exchange.assert_called_once()
            self.assertEqual(self.post('google/', {'code': 'test-code', 'state': query['state'][0]}).status_code, 400)
    def test_google_rejects_unsolicited_token(self):
        self.assertEqual(self.post('google/', {'access_token': 'unsolicited'}).status_code, 400)
