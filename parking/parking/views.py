from rest_framework import serializers as drf_serializers
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.shortcuts import render
from decimal import Decimal

from .models import ParkingPlace, Vehicle, ParkingSession, Subscription, ParkingAlert, Tariff
from .serializers import (
    ParkingPlaceSerializer, VehicleSerializer, ParkingSessionSerializer,
    SessionEntrySerializer, SubscriptionSerializer, ParkingAlertSerializer,
    TariffSerializer
)
from .parking_service import create_entry_session, close_session


def dashboard_view(request):
    return render(request, 'dashboard.html')


class ParkingPlaceViewSet(viewsets.ModelViewSet):
    queryset = ParkingPlace.objects.all()
    serializer_class = ParkingPlaceSerializer

    @action(detail=False, methods=['get'])
    def available(self, request):
        available_places = self.get_queryset().filter(is_occupied=False, is_reserved=False)
        serializer = self.get_serializer(available_places, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_floor(self, request):
        floor = request.query_params.get('floor')
        qs = self.get_queryset()
        if floor:
            qs = qs.filter(floor=floor)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        total = qs.count()
        occupied = qs.filter(is_occupied=True).count()
        available = qs.filter(is_occupied=False, is_reserved=False).count()
        reserved = qs.filter(is_reserved=True).count()
        rate = round((occupied / total * 100) if total > 0 else 0, 1)

        by_floor = []
        floors = qs.values_list('floor', flat=True).distinct().order_by('floor')
        for f in floors:
            floor_places = qs.filter(floor=f)
            by_floor.append({
                'floor': f,
                'total': floor_places.count(),
                'occupied': floor_places.filter(is_occupied=True).count(),
                'available': floor_places.filter(is_occupied=False, is_reserved=False).count(),
            })

        by_type = []
        for ptype, _ in ParkingPlace.PLACE_TYPES:
            type_places = qs.filter(place_type=ptype)
            by_type.append({
                'type': ptype,
                'total': type_places.count(),
                'occupied': type_places.filter(is_occupied=True).count(),
            })

        return Response({
            'total': total,
            'occupied': occupied,
            'available': available,
            'reserved': reserved,
            'occupancy_rate': rate,
            'by_floor': by_floor,
            'by_type': by_type,
        })


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.select_related('owner').all()
    serializer_class = VehicleSerializer

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        vehicle = self.get_object()
        sessions = ParkingSession.objects.filter(vehicle=vehicle).order_by('-entry_time')[:50]
        serializer = ParkingSessionSerializer(sessions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def active_session(self, request, pk=None):
        vehicle = self.get_object()
        session = ParkingSession.objects.filter(vehicle=vehicle, is_active=True).first()
        if session:
            return Response(ParkingSessionSerializer(session).data)
        return Response({'detail': 'No active session'}, status=404)


class ParkingSessionViewSet(viewsets.ModelViewSet):
    queryset = ParkingSession.objects.select_related('vehicle', 'parking_place').all()
    serializer_class = ParkingSessionSerializer

    @action(detail=False, methods=['get'])
    def active(self, request):
        active_sessions = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(active_sessions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def history(self, request):
        """Full history with filters."""
        qs = self.get_queryset().filter(is_active=False)
        date_from = request.query_params.get('from')
        date_to = request.query_params.get('to')
        plate = request.query_params.get('plate')
        if date_from:
            qs = qs.filter(entry_time__date__gte=date_from)
        if date_to:
            qs = qs.filter(entry_time__date__lte=date_to)
        if plate:
            qs = qs.filter(vehicle__plate_number__icontains=plate)
        page = self.paginate_queryset(qs[:200])
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(qs[:200], many=True).data)

    @action(detail=False, methods=['post'], serializer_class=SessionEntrySerializer)
    def entry(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.validated_data['vehicle_id']
        notes = serializer.validated_data.get('notes', '')
        session = create_entry_session(vehicle, notes)
        return Response(ParkingSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], serializer_class=drf_serializers.Serializer)
    def exit(self, request, pk=None):
        session = close_session(pk)
        return Response(ParkingSessionSerializer(session).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def qr_code(self, request, pk=None):
        """Returns the QR code image URL for a session."""
        try:
            session = ParkingSession.objects.get(id=pk)
        except ParkingSession.DoesNotExist:
            return Response({'error': 'Session not found'}, status=404)
        # Generate if missing
        if not session.qr_code:
            from .parking_service import generate_qr_code
            session = generate_qr_code(session)
        if session.qr_code:
            url = request.build_absolute_uri(session.qr_code.url)
            return Response({'qr_url': url, 'session_id': session.id})
        return Response({'error': 'QR code could not be generated'}, status=500)

    @action(detail=False, methods=['get'])
    def revenue(self, request):
        today = timezone.now().date()
        first_of_month = today.replace(day=1)
        revenue_today = ParkingSession.objects.filter(
            is_active=False, exit_time__date=today
        ).aggregate(total=Sum('total_price'))['total'] or Decimal('0')
        revenue_month = ParkingSession.objects.filter(
            is_active=False, exit_time__date__gte=first_of_month
        ).aggregate(total=Sum('total_price'))['total'] or Decimal('0')
        revenue_total = ParkingSession.objects.filter(
            is_active=False
        ).aggregate(total=Sum('total_price'))['total'] or Decimal('0')
        return Response({
            'today': str(revenue_today),
            'month': str(revenue_month),
            'total': str(revenue_total),
        })


class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.select_related('user', 'vehicle').all()
    serializer_class = SubscriptionSerializer

    @action(detail=False, methods=['get'])
    def active(self, request):
        today = timezone.now().date()
        active = self.get_queryset().filter(status='active', end_date__gte=today)
        return Response(self.get_serializer(active, many=True).data)

    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        soon = timezone.now().date() + timezone.timedelta(days=7)
        today = timezone.now().date()
        subs = self.get_queryset().filter(status='active', end_date__lte=soon, end_date__gte=today)
        return Response(self.get_serializer(subs, many=True).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        sub = self.get_object()
        sub.status = 'cancelled'
        sub.save()
        return Response(self.get_serializer(sub).data)


class ParkingAlertViewSet(viewsets.ModelViewSet):
    queryset = ParkingAlert.objects.all()
    serializer_class = ParkingAlertSerializer

    @action(detail=False, methods=['get'])
    def unread(self, request):
        alerts = self.get_queryset().filter(is_read=False)[:20]
        return Response(self.get_serializer(alerts, many=True).data)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        alert = self.get_object()
        alert.is_read = True
        alert.save()
        return Response({'status': 'read'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        ParkingAlert.objects.filter(is_read=False).update(is_read=True)
        return Response({'status': 'all marked as read'})


class TariffViewSet(viewsets.ModelViewSet):
    queryset = Tariff.objects.all()
    serializer_class = TariffSerializer
