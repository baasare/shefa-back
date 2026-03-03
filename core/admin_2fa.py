"""
Two-Factor Authentication (2FA) for Django admin.

Uses django-otp for TOTP-based 2FA.
"""
from django.contrib import admin
from django.contrib.auth.decorators import user_passes_test
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.contrib import messages
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.util import random_hex
import qrcode
import io
import base64


class Admin2FAMixin:
    """
    Mixin to add 2FA requirements to admin classes.

    Add this to any ModelAdmin that should require 2FA.
    """

    def has_module_permission(self, request):
        """Only allow access if 2FA is verified."""
        if not request.user.is_authenticated:
            return False

        # Superusers must have 2FA
        if request.user.is_superuser:
            return request.user.is_verified()

        # Other staff can access without 2FA (for now)
        return super().has_module_permission(request)


def require_2fa_for_admin(request):
    """Check if user has 2FA enabled and verified."""
    if not request.user.is_authenticated:
        return False

    if request.user.is_superuser:
        # Superusers must have 2FA
        devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)
        return devices.exists() and request.user.is_verified()

    return True


# Custom admin site with 2FA
class SecureAdminSite(admin.AdminSite):
    """
    Custom admin site that enforces 2FA for superusers.
    """

    site_title = 'ShefaFx Secure Admin'
    site_header = 'ShefaFx Administration'
    index_title = 'Dashboard'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('2fa/setup/', self.admin_view(self.setup_2fa), name='setup_2fa'),
            path('2fa/verify/', self.admin_view(self.verify_2fa), name='verify_2fa'),
            path('2fa/disable/', self.admin_view(self.disable_2fa), name='disable_2fa'),
        ]
        return custom_urls + urls

    def has_permission(self, request):
        """Check if user has permission to access admin."""
        has_perm = super().has_permission(request)

        if not has_perm:
            return False

        # If superuser, check 2FA
        if request.user.is_superuser:
            devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)

            # If no devices, redirect to setup
            if not devices.exists():
                return True  # Allow access to setup 2FA

            # If device exists but not verified in this session
            if not request.user.is_verified():
                return False

        return True

    def setup_2fa(self, request):
        """Setup 2FA for user."""
        if request.method == 'POST':
            token = request.POST.get('token')

            # Get or create device
            device = TOTPDevice.objects.filter(user=request.user).first()
            if not device:
                messages.error(request, "No device found. Please try again.")
                return redirect('admin:setup_2fa')

            # Verify token
            if device.verify_token(token):
                device.confirmed = True
                device.save()
                # Mark user as verified for this session
                from django_otp import login as otp_login
                otp_login(request, device)
                messages.success(request, "2FA has been successfully enabled!")
                return redirect('admin:index')
            else:
                messages.error(request, "Invalid token. Please try again.")

        # Generate new device if doesn't exist
        device = TOTPDevice.objects.filter(user=request.user).first()
        if not device:
            device = TOTPDevice.objects.create(
                user=request.user,
                name=f"{request.user.username}'s device",
                confirmed=False,
                key=random_hex(20)
            )

        # Generate QR code
        otp_uri = device.config_url
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(otp_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()

        context = {
            'site_title': self.site_title,
            'site_header': self.site_header,
            'device': device,
            'qr_code': img_str,
            'secret_key': device.key,
        }

        return render(request, 'admin/2fa_setup.html', context)

    def verify_2fa(self, request):
        """Verify 2FA token."""
        if request.method == 'POST':
            token = request.POST.get('token')

            # Get user's device
            device = TOTPDevice.objects.filter(
                user=request.user,
                confirmed=True
            ).first()

            if device and device.verify_token(token):
                # Mark user as verified for this session
                from django_otp import login as otp_login
                otp_login(request, device)
                messages.success(request, "2FA verification successful!")
                return redirect('admin:index')
            else:
                messages.error(request, "Invalid token. Please try again.")

        context = {
            'site_title': self.site_title,
            'site_header': self.site_header,
        }

        return render(request, 'admin/2fa_verify.html', context)

    def disable_2fa(self, request):
        """Disable 2FA for user."""
        if request.method == 'POST':
            confirm = request.POST.get('confirm')

            if confirm == 'yes':
                TOTPDevice.objects.filter(user=request.user).delete()
                messages.success(request, "2FA has been disabled.")
                return redirect('admin:index')

        context = {
            'site_title': self.site_title,
            'site_header': self.site_header,
        }

        return render(request, 'admin/2fa_disable.html', context)


# Replace default admin site
secure_admin_site = SecureAdminSite(name='secure_admin')


# Middleware to enforce 2FA verification
class Admin2FAMiddleware:
    """
    Middleware to enforce 2FA for admin access.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if accessing admin
        if request.path.startswith('/admin/'):
            if request.user.is_authenticated and request.user.is_superuser:
                # Check if has 2FA device
                devices = TOTPDevice.objects.filter(
                    user=request.user,
                    confirmed=True
                )

                # If no device, redirect to setup
                if not devices.exists() and not request.path.startswith('/admin/2fa/'):
                    return redirect('admin:setup_2fa')

                # If device exists but not verified
                if devices.exists() and not request.user.is_verified():
                    if not request.path.startswith('/admin/2fa/') and not request.path.startswith('/admin/login/'):
                        return redirect('admin:verify_2fa')

        response = self.get_response(request)
        return response


# Installation instructions comment
"""
INSTALLATION:

1. Install django-otp:
   pip install django-otp qrcode[pil]

2. Add to INSTALLED_APPS in settings.py:
   INSTALLED_APPS = [
       ...
       'django_otp',
       'django_otp.plugins.otp_totp',
       'django_otp.plugins.otp_static',
   ]

3. Add middleware in settings.py:
   MIDDLEWARE = [
       ...
       'django.contrib.auth.middleware.AuthenticationMiddleware',
       'django_otp.middleware.OTPMiddleware',  # Add this after AuthenticationMiddleware
       'core.admin_2fa.Admin2FAMiddleware',   # Add this for admin 2FA enforcement
   ]

4. Run migrations:
   python manage.py migrate

5. In your main urls.py, replace default admin:
   from core.admin_2fa import secure_admin_site

   urlpatterns = [
       path('admin/', secure_admin_site.urls),  # Use secure admin
       ...
   ]

6. Create templates/admin/2fa_setup.html, 2fa_verify.html, 2fa_disable.html

7. First superuser login will prompt for 2FA setup with QR code
"""
