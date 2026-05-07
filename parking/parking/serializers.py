from rest_framework import serializers
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.utils import timezone
from .models import ParkingPlace, Vehicle, ParkingSession, Subscription, ParkingAlert, Tariff, Booking

User = get_user_model()


class ParkingPlaceSerializer(serializers.ModelSerializer):
    status = serializers.ReadOnlyField()
    reserved_future = serializers.SerializerMethodField()
    next_booking_start = serializers.SerializerMethodField()

    class Meta:
        model = ParkingPlace
        fields = '__all__'

    def get_reserved_future(self, obj):
        now = timezone.now()
        return Booking.objects.filter(parking_place=obj, status__in=['confirmed', 'active'], start_time__gt=now).exists()

    def get_next_booking_start(self, obj):
        now = timezone.now()
        b = Booking.objects.filter(parking_place=obj, status__in=['confirmed', 'active'], start_time__gt=now).order_by('start_time').first()
        return b.start_time if b else None


class VehicleSerializer(serializers.ModelSerializer):
    owner_email = serializers.CharField(source='owner.email', read_only=True)
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())

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


class BookingSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    vehicle_plate = serializers.CharField(source='vehicle.plate_number', read_only=True)
    place_number = serializers.CharField(source='parking_place.number', read_only=True)

    class Meta:
        model = Booking
        fields = '__all__'


class BookingCreateSerializer(serializers.Serializer):
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField(required=False, allow_null=True)
    parking_place = serializers.PrimaryKeyRelatedField(queryset=ParkingPlace.objects.all(), required=False, allow_null=True)

    def validate(self, data):
        # If end_time not provided, default to +1 hour
        if not data.get('end_time'):
            data['end_time'] = data['start_time'] + timedelta(hours=1)
        if data['start_time'] >= data['end_time']:
            raise serializers.ValidationError("End time must be after start time.")
        # Allow a 5-minute buffer in case the user selects the exact current minute
        if data['start_time'] < timezone.now() - timedelta(minutes=5):
            raise serializers.ValidationError("Booking start time cannot be in the past.")
        return data
