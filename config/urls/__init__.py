from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from backend.core.admin_2fa import secure_admin_site

urlpatterns = [
    path('admin/', secure_admin_site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)