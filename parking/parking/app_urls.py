from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ParkingPlaceViewSet, VehicleViewSet, ParkingSessionViewSet

router = DefaultRouter()
router.register(r'places', ParkingPlaceViewSet, basename='parkingplace')
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'sessions', ParkingSessionViewSet, basename='parkingsession')

urlpatterns = router.urls