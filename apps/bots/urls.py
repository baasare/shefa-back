from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.bots.views import BotViewSet

router = DefaultRouter()
router.register('', BotViewSet, basename='bot')

urlpatterns = [path('', include(router.urls))]
