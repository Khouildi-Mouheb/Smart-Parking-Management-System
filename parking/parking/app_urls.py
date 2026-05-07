from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ParkingPlaceViewSet, VehicleViewSet, ParkingSessionViewSet,
    SubscriptionViewSet, ParkingAlertViewSet, TariffViewSet
)

router = DefaultRouter()
router.register(r'places', ParkingPlaceViewSet, basename='parkingplace')
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'sessions', ParkingSessionViewSet, basename='parkingsession')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'alerts', ParkingAlertViewSet, basename='alert')
router.register(r'tariffs', TariffViewSet, basename='tariff')

urlpatterns = router.urls
