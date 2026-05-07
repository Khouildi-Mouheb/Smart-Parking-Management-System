from rest_framework import serializers
from .models import ParkingPlace, Vehicle, ParkingSession, Subscription, ParkingAlert, Tariff
from django.contrib.auth import get_user_model

User = get_user_model()


class ParkingPlaceSerializer(serializers.ModelSerializer):
    status = serializers.ReadOnlyField()

    class Meta:
        model = ParkingPlace
        fields = '__all__'


class VehicleSerializer(serializers.ModelSerializer):
    owner_email = serializers.CharField(source='owner.email', read_only=True)

    class Meta:
        model = Vehicle
        fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    is_valid = serializers.ReadOnlyField()
    days_remaining = serializers.ReadOnlyField()
    user_email = serializers.CharField(source='user.email', read_only=True)
    vehicle_plate = serializers.CharField(source='vehicle.plate_number', read_only=True)

    class Meta:
        model = Subscription
        fields = '__all__'


class ParkingSessionSerializer(serializers.ModelSerializer):
    vehicle_plate = serializers.CharField(source='vehicle.plate_number', read_only=True)
    place_number = serializers.CharField(source='parking_place.number', read_only=True)
    place_floor = serializers.IntegerField(source='parking_place.floor', read_only=True)
    duration_display = serializers.ReadOnlyField()
    duration_minutes = serializers.ReadOnlyField()

    class Meta:
        model = ParkingSession
        fields = '__all__'


class SessionEntrySerializer(serializers.Serializer):
    vehicle_id = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    notes = serializers.CharField(required=False, allow_blank=True)


class ParkingAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkingAlert
        fields = '__all__'


class TariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tariff
        fields = '__all__'


class DashboardStatsSerializer(serializers.Serializer):
    total_places = serializers.IntegerField()
    occupied_places = serializers.IntegerField()
    available_places = serializers.IntegerField()
    reserved_places = serializers.IntegerField()
    occupancy_rate = serializers.FloatField()
    active_sessions = serializers.IntegerField()
    total_revenue_today = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_revenue_month = serializers.DecimalField(max_digits=10, decimal_places=2)
    active_subscriptions = serializers.IntegerField()
    unread_alerts = serializers.IntegerField()
    by_floor = serializers.ListField()
    by_type = serializers.ListField()
