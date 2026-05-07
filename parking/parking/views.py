from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ParkingPlace, Vehicle, ParkingSession
from .serializers import ParkingPlaceSerializer, VehicleSerializer, ParkingSessionSerializer, SessionEntrySerializer
from .services.parking_service import create_entry_session, close_session

class ParkingPlaceViewSet(viewsets.ModelViewSet):
    queryset = ParkingPlace.objects.all()
    serializer_class = ParkingPlaceSerializer

    @action(detail=False, methods=['get'])
    def available(self, request):
        """Returns a list of all currently free parking places."""
        available_places = self.get_queryset().filter(is_occupied=False)
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
        serializer = self.get_serializer(active_sessions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], serializer_class=SessionEntrySerializer)
    def entry(self, request):
        """Registers a vehicle's entry and creates an active session."""
        serializer = SessionEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            vehicle = Vehicle.objects.get(id=serializer.validated_data['vehicle_id'])
            session = create_entry_session(vehicle)
            return Response(ParkingSessionSerializer(session).data, status=status.HTTP_201_CREATED)
        except Vehicle.DoesNotExist:
            return Response({'detail': 'Vehicle not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def exit(self, request, pk=None):
        """Registers a vehicle's exit, computes total cost, and frees the parking place."""
        try:
            session = close_session(pk)
            return Response(ParkingSessionSerializer(session).data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)