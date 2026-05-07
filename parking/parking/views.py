from rest_framework import serializers as drf_serializers
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from decimal import Decimal

from .models import ParkingPlace, Vehicle, ParkingSession, Subscription, ParkingAlert, Tariff, Booking
from .serializers import (
    ParkingPlaceSerializer, VehicleSerializer, ParkingSessionSerializer,
    SessionEntrySerializer, SubscriptionSerializer, ParkingAlertSerializer,
    TariffSerializer, BookingSerializer, BookingCreateSerializer
)
from .parking_service import create_entry_session, close_session, create_booking


User = get_user_model()


@login_required(login_url='/login/')
def dashboard_view(request):
    # Route Admins/Agents to the Admin Dashboard, Clients to the Parking Places map
    if request.user.role in ['admin', 'agent'] or request.user.is_superuser:
        return render(request, 'dashboard.html')
    return redirect('/places/')

@login_required(login_url='/login/')
def parking_places_view(request):
    return render(request, 'parking_places.html')


class ParkingPlaceViewSet(viewsets.ModelViewSet):
    queryset = ParkingPlace.objects.all()
    serializer_class = ParkingPlaceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Superusers see everything
        if user.is_authenticated and user.is_superuser:
            return qs
        # If user belongs to a company, restrict to that company
        company = getattr(user, 'company', None)
        if company:
            qs = qs.filter(company=company)
            # Optional query filters from the UI
            search = self.request.query_params.get('search')
            floor = self.request.query_params.get('floor')
            if search:
                qs = qs.filter(number__icontains=search)
            if floor:
                try:
                    qs = qs.filter(floor=int(floor))
                except ValueError:
                    pass
            return qs
        # Otherwise no access
        return qs.none()

    def create(self, request, *args, **kwargs):
        """Ensure created places are associated with the user's company (if any)
        and validate uniqueness per company."""
        data = request.data.copy()
        user = request.user
        company = getattr(user, 'company', None)
        # If non-superuser and company exists, force assign company
        if company and not user.is_superuser:
            data['company'] = company.id

        # Basic duplicate check: same number + floor within the company
        number = data.get('number')
        floor = data.get('floor')
        if not number:
            return Response({'error': 'Place number is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if floor in (None, ''):
            return Response({'error': 'Floor is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            floor_val = int(floor)
        except Exception:
            return Response({'error': 'Floor must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = ParkingPlace.objects.filter(number=number, floor=floor_val)
        if company:
            existing = existing.filter(company=company)
        else:
            existing = existing.filter(company__isnull=True)
        if existing.exists():
            return Response({'error': 'Place with this number and floor already exists for this company.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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

    @action(detail=True, methods=['post'])
    def reserve(self, request, pk=None):
        place = self.get_object()
        if place.is_occupied or place.is_reserved:
            return Response({'error': 'Place is not available for reservation.'}, status=status.HTTP_400_BAD_REQUEST)
        place.is_reserved = True
        place.reserved_by = request.user
        place.save()
        return Response({'status': 'reserved'})

    @action(detail=True, methods=['post'])
    def unreserve(self, request, pk=None):
        place = self.get_object()
        if place.reserved_by != request.user and request.user.role != 'admin':
            return Response({'error': 'Not authorized to cancel this reservation.'}, status=status.HTTP_403_FORBIDDEN)
        place.is_reserved = False
        place.reserved_by = None
        place.save()
        return Response({'status': 'unreserved'})

    @action(detail=True, methods=['post'])
    def occupy(self, request, pk=None):
        """Force-occupy a specific place for the given vehicle (quick entry without booking)."""
        place = self.get_object()
        if place.is_occupied:
            return Response({'error': 'Place already occupied.'}, status=status.HTTP_400_BAD_REQUEST)
        vehicle_id = request.data.get('vehicle_id')
        if not vehicle_id:
            return Response({'error': 'vehicle_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            vehicle = Vehicle.objects.get(id=vehicle_id)
        except Vehicle.DoesNotExist:
            return Response({'error': 'Vehicle not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Create session and assign this specific place
        from .parking_service import create_entry_session
        # Temporarily mark place occupied so create_entry_session won't pick it again
        place.is_occupied = True
        place.save()
        try:
            session = ParkingSession.objects.create(vehicle=vehicle, parking_place=place, is_active=True)
            # generate QR
            from .parking_service import generate_qr_code
            session = generate_qr_code(session)
        except Exception as e:
            place.is_occupied = False
            place.save()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ParkingSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.select_related('owner').all()
    serializer_class = VehicleSerializer

    def perform_create(self, serializer):
        # Ensure the owner is always the requesting user
        serializer.save(owner=self.request.user)
    
    def perform_update(self, serializer):
        # Prevent clients from changing the owner; always set to the requesting user
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        # Allow deletion only by the owner or admin users
        from rest_framework.exceptions import PermissionDenied
        if getattr(instance, 'owner', None) != self.request.user and getattr(self.request.user, 'role', None) != 'admin':
            raise PermissionDenied('You are not allowed to delete this vehicle.')
        return super().perform_destroy(instance)

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        if user.role == 'client':
            return qs.filter(owner=user)
        company = getattr(user, 'company', None)
        if company:
            return qs.filter(owner__company=company)
        return qs.none()

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

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        company = getattr(user, 'company', None)
        if company:
            return qs.filter(parking_place__company=company)
        return qs.filter(vehicle__owner=user)

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
        # Prefer places belonging to the user's company
        company = getattr(request.user, 'company', None)
        session = create_entry_session(vehicle, notes, company=company)
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

    @action(detail=True, methods=['get'])
    def invoice(self, request, pk=None):
        """Generate a PDF invoice for a closed session."""
        try:
            session = ParkingSession.objects.get(id=pk)
        except ParkingSession.DoesNotExist:
            return Response({'error': 'Session not found.'}, status=404)
        if session.is_active:
            return Response({'error': 'Session must be closed to generate invoice.'}, status=400)

        # Generate a simple PDF invoice using reportlab
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except Exception:
            return Response({'error': 'PDF generation library not available.'}, status=500)

        from io import BytesIO
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        text = c.beginText(40, 800)
        text.setFont('Helvetica', 12)
        text.textLine('Parking Invoice')
        text.textLine('')
        text.textLine(f'Session ID: {session.id}')
        text.textLine(f'Plate: {session.vehicle.plate_number}')
        text.textLine(f'Entry: {session.entry_time.strftime("%Y-%m-%d %H:%M")}')
        text.textLine(f'Exit: {session.exit_time.strftime("%Y-%m-%d %H:%M") if session.exit_time else "-"}')
        text.textLine(f'Duration: {session.duration_display}')
        text.textLine(f'Total: {session.total_price or "0.00"} DT')
        text.textLine('')
        company = getattr(session.parking_place, 'company', None)
        if company:
            text.textLine(f'Company: {company.name}')
        c.drawText(text)
        c.showPage()
        c.save()
        buffer.seek(0)

        from django.http import FileResponse
        return FileResponse(buffer, as_attachment=True, filename=f'invoice_session_{session.id}.pdf')

    @action(detail=False, methods=['get'])
    def revenue(self, request):
        today = timezone.now().date()
        first_of_month = today.replace(day=1)
        
        qs = self.get_queryset().filter(is_active=False)
        
        revenue_today = qs.filter(
            exit_time__date=today
        ).aggregate(total=Sum('total_price'))['total'] or Decimal('0')
        revenue_month = qs.filter(
            exit_time__date__gte=first_of_month
        ).aggregate(total=Sum('total_price'))['total'] or Decimal('0')
        revenue_total = qs.aggregate(total=Sum('total_price'))['total'] or Decimal('0')
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


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer

    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        return BookingSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Booking.objects.none()
        if user.is_superuser:
            return Booking.objects.all().select_related('user', 'vehicle', 'parking_place')
            
        if user.role == 'client':
            return Booking.objects.filter(user=user).select_related('vehicle', 'parking_place')
        company = getattr(user, 'company', None)
        if company:
            return Booking.objects.filter(parking_place__company=company).select_related('user', 'vehicle', 'parking_place')
        return Booking.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        vehicle = serializer.validated_data['vehicle']
        if request.user.role == 'client' and vehicle.owner != request.user:
            return Response({'error': 'You can only book for your own vehicles.'}, status=status.HTTP_403_FORBIDDEN)

        parking_place = serializer.validated_data.get('parking_place')
        try:
            booking = create_booking(user=request.user, vehicle=vehicle, start_time=serializer.validated_data['start_time'], end_time=serializer.validated_data['end_time'], parking_place=parking_place)
        except ValidationError as e:
            # e may be a DRF ValidationError or Django one
            msg = getattr(e, 'detail', None) or str(e)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

        response_serializer = self.serializer_class(booking, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def invoice(self, request, pk=None):
        """Generate a PDF ticket/facture for a booking."""
        booking = self.get_object()

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            return Response({'error': 'PDF generation library not available. Install with: pip install reportlab'}, status=500)

        from io import BytesIO
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        text = c.beginText(40, 800)
        text.setFont('Helvetica', 12)
        text.textLine('Parking Booking Facture')
        text.textLine('')
        text.textLine(f'Booking ID: {booking.id}')
        text.textLine(f'User: {booking.user.full_name} ({booking.user.email})')
        text.textLine(f'Plate: {booking.vehicle.plate_number}')
        text.textLine(f'Vehicle: {booking.vehicle.brand} {booking.vehicle.model}')
        text.textLine(f'Place: {booking.parking_place.number if booking.parking_place else "Any"}')
        text.textLine(f'From: {booking.start_time.strftime("%Y-%m-%d %H:%M")}')
        text.textLine(f'To: {booking.end_time.strftime("%Y-%m-%d %H:%M")}')
        text.textLine(f'Estimated Price: {booking.estimated_price} DT')
        text.textLine(f'Status: {booking.status}')
        c.drawText(text)
        c.showPage()
        c.save()
        buffer.seek(0)

        from django.http import FileResponse
        return FileResponse(buffer, as_attachment=True, filename=f'facture_booking_{booking.id}.pdf')
