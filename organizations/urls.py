from django.urls import path, include
from rest_framework.routers import DefaultRouter
from organizations.views import (
    OrganizationViewSet, TariffViewSet, SubscriptionViewSet, OrganizationLoginView
)

router = DefaultRouter()
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'tariffs', TariffViewSet, basename='tariff')
router.register(r'organizations', OrganizationViewSet, basename='organization')

urlpatterns = [
    path('login/', OrganizationLoginView.as_view(), name='organization-login'),
    path('', include(router.urls)),
]