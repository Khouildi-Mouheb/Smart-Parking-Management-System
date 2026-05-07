from rest_framework import serializers
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ParkingPlace, Vehicle, ParkingSession
from .serializers import ParkingPlaceSerializer, VehicleSerializer, ParkingSessionSerializer, SessionEntrySerializer
from .parking_service import create_entry_session, close_session

class ParkingPlaceViewSet(viewsets.ModelViewSet):
    queryset = ParkingPlace.objects.all()
    serializer_class = ParkingPlaceSerializer

    @action(detail=False, methods=['get'])
    def available(self, request):
        """Returns a list of all currently free parking places."""
        available_places = self.get_queryset().filter(is_occupied=False)

        page = self.paginate_queryset(available_places)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(available_places, many=True)
        return Response(serializer.data)

class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer

class ParkingSessionViewSet(viewsets.ModelViewSet):
    queryset = ParkingSession.objects.all()
    serializer_class = ParkingSessionSerializer

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Returns a list of all currently ongoing parking sessions."""
        active_sessions = self.get_queryset().filter(is_active=True)

        page = self.paginate_queryset(active_sessions)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(active_sessions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], serializer_class=SessionEntrySerializer)
    def entry(self, request):
        """Registers a vehicle's entry and creates an active session."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.validated_data['vehicle_id']
        session = create_entry_session(vehicle)
        return Response(ParkingSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], serializer_class=serializers.Serializer)
    def exit(self, request, pk=None):
        """Registers a vehicle's exit, computes total cost, and frees the parking place."""
        session = close_session(pk)
        return Response(ParkingSessionSerializer(session).data, status=status.HTTP_200_OK)