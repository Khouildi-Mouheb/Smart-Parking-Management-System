from rest_framework import serializers
from .models import ParkingPlace, Vehicle, ParkingSession

class ParkingPlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkingPlace
        fields = '__all__'

class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = '__all__'
        read_only_fields = ('created_at',)

class ParkingSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkingSession
        fields = '__all__'
        read_only_fields = ('entry_time', 'exit_time', 'total_price', 'is_active', 'qr_code')


class SessionEntrySerializer(serializers.Serializer):
    """Serializer specifically for triggering an entry action."""
    vehicle_id = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())