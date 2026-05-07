from django.contrib import admin
from .models import ParkingPlace, Vehicle, ParkingSession

@admin.register(ParkingPlace)
class ParkingPlaceAdmin(admin.ModelAdmin):
    list_display = ('number', 'floor', 'is_occupied', 'created_at')
    list_filter = ('floor', 'is_occupied')
    search_fields = ('number',)
    ordering = ('floor', 'number')

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('plate_number', 'brand', 'color', 'owner', 'created_at')
    list_filter = ('brand', 'color')
    search_fields = ('plate_number', 'owner__email', 'owner__username')
    ordering = ('-created_at',)

@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'parking_place', 'entry_time', 'exit_time', 'is_active', 'total_price')
    list_filter = ('is_active', 'entry_time')
    search_fields = ('vehicle__plate_number', 'parking_place__number')
    readonly_fields = ('entry_time', 'exit_time', 'total_price')
    ordering = ('-entry_time',)