from django.contrib import admin
from .models import ParkingPlace, Vehicle, ParkingSession, Subscription, ParkingAlert, Tariff

@admin.register(ParkingPlace)
class ParkingPlaceAdmin(admin.ModelAdmin):
    list_display = ['number', 'floor', 'place_type', 'is_occupied', 'is_reserved', 'hourly_rate']
    list_filter = ['floor', 'place_type', 'is_occupied', 'is_reserved']
    search_fields = ['number']

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['plate_number', 'brand', 'model', 'color', 'vehicle_type', 'owner']
    search_fields = ['plate_number', 'brand']

@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'vehicle', 'parking_place', 'entry_time', 'exit_time', 'total_price', 'is_active', 'is_subscription_session']
    list_filter = ['is_active', 'is_subscription_session']
    search_fields = ['vehicle__plate_number']

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'vehicle', 'plan', 'status', 'price', 'start_date', 'end_date', 'auto_renew']
    list_filter = ['plan', 'status']
    search_fields = ['user__email', 'vehicle__plate_number']

@admin.register(ParkingAlert)
class ParkingAlertAdmin(admin.ModelAdmin):
    list_display = ['alert_type', 'severity', 'message', 'is_read', 'created_at']
    list_filter = ['severity', 'is_read', 'alert_type']

@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ['name', 'place_type', 'base_rate', 'hourly_rate', 'daily_max', 'is_active']
