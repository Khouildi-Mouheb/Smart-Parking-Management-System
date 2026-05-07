import math
import qrcode
from io import BytesIO
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.core.files.base import ContentFile
from rest_framework.exceptions import ValidationError
from .models import ParkingPlace, ParkingSession, Vehicle, Tariff, ParkingAlert, Subscription, Booking


def assign_free_place(place_type='standard', company=None):
    """Finds and returns the first available parking place of the given type."""
    qs = ParkingPlace.objects.filter(
        is_occupied=False,
        is_reserved=False,
        place_type=place_type
    )
    if company:
        qs = qs.filter(company=company)
    place = qs.order_by('floor', 'number').first()
    if not place:
        # Fallback to any available place (optionally within company)
        qs = ParkingPlace.objects.filter(is_occupied=False, is_reserved=False)
        if company:
            qs = qs.filter(company=company)
        place = qs.order_by('floor', 'number').first()
    return place


def calculate_price(session, tariff=None):
    """Calculates price based on duration and tariff."""
    duration = session.exit_time - session.entry_time
    hours = max(1, math.ceil(duration.total_seconds() / 3600.0))

    if tariff:
        base = tariff.base_rate
        hourly = tariff.hourly_rate
        daily_max = tariff.daily_max
    else:
        base = Decimal('2.00')
        hourly = Decimal('1.50')
        daily_max = Decimal('20.00')

    if hours <= 1:
        price = base
    else:
        price = base + Decimal(hours - 1) * hourly

    # Cap at daily max per day
    days = max(1, math.ceil(duration.total_seconds() / 86400.0))
    price = min(price, daily_max * days)
    return price


def generate_qr_code(session):
    """Generates a QR code for the parking session ticket."""
    qr_data = (
        f"=== PARKING TICKET ===\n"
        f"Session ID: {session.id}\n"
        f"Plate: {session.vehicle.plate_number}\n"
        f"Vehicle: {session.vehicle.brand} {session.vehicle.model}\n"
        f"Place: {session.parking_place.number} (Floor {session.parking_place.floor})\n"
        f"Entry: {session.entry_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"Subscription: {'Yes' if session.is_subscription_session else 'No'}\n"
    )
    qr = qrcode.QRCode(version=2, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    session.qr_code.save(f"session_{session.id}_qr.png", ContentFile(buffer.getvalue()), save=True)
    return session


def generate_booking_qr_code(booking):
    """Generates a QR code for the booking."""
    qr_data = (
        f"=== PARKING BOOKING ===\n"
        f"Booking ID: {booking.id}\n"
        f"User: {booking.user.full_name}\n"
        f"Plate: {booking.vehicle.plate_number}\n"
        f"Place: {booking.parking_place.number} (Floor {booking.parking_place.floor})\n"
        f"From: {booking.start_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"To: {booking.end_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"Price: {booking.estimated_price} DT\n"
    )
    qr = qrcode.QRCode(version=2, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    booking.qr_code.save(f"booking_{booking.id}_qr.png", ContentFile(buffer.getvalue()), save=True)
    return booking


def check_and_create_alerts():
    """Check occupancy and create alerts as needed."""
    total = ParkingPlace.objects.count()
    occupied = ParkingPlace.objects.filter(is_occupied=True).count()
    if total == 0:
        return

    rate = (occupied / total) * 100

    if rate >= 100:
        ParkingAlert.objects.create(
            alert_type='full',
            severity='critical',
            message=f"Parking is FULL! All {total} places are occupied."
        )
    elif rate >= 80:
        ParkingAlert.objects.create(
            alert_type='almost_full',
            severity='warning',
            message=f"Parking is {rate:.0f}% full! Only {total - occupied} places left."
        )

    # Check subscription expiries
    from django.contrib.auth import get_user_model
    User = get_user_model()
    soon = timezone.now().date() + timezone.timedelta(days=3)
    expiring = Subscription.objects.filter(status='active', end_date__lte=soon, end_date__gte=timezone.now().date())
    for sub in expiring:
        ParkingAlert.objects.get_or_create(
            alert_type='subscription_expiry',
            user=sub.user,
            is_read=False,
            defaults={
                'severity': 'warning',
                'message': f"Your {sub.plan} subscription expires on {sub.end_date}. Renew now!"
            }
        )


@transaction.atomic
def create_entry_session(vehicle, notes='', company=None):
    """Assigns a parking place to a vehicle and opens a session."""
    if ParkingSession.objects.filter(vehicle=vehicle, is_active=True).exists():
        raise ValidationError("This vehicle already has an active parking session.")

    # Check if vehicle has active subscription
    active_sub = Subscription.objects.filter(
        vehicle=vehicle,
        status='active',
        end_date__gte=timezone.now().date()
    ).first()

    place = assign_free_place(company=company)
    if not place:
        raise ValidationError("No parking places available.")

    place.is_occupied = True
    place.save()

    session = ParkingSession.objects.create(
        vehicle=vehicle,
        parking_place=place,
        is_active=True,
        is_subscription_session=bool(active_sub),
        subscription=active_sub,
        notes=notes or ''
    )

    generate_qr_code(session)
    check_and_create_alerts()
    return session


@transaction.atomic
def create_booking(user, vehicle, start_time, end_time, parking_place=None):
    """
    Creates a booking for a user, finds a spot, calculates price, and returns the booking.
    """
    # 1. Validate times
    if start_time >= end_time:
        raise ValidationError("End time must be after start time.")
    if start_time < timezone.now():
        raise ValidationError("Booking start time cannot be in the past.")

    # 2. Find an available parking place (or validate requested one)
    conflicting_bookings = Booking.objects.filter(
        status__in=['confirmed', 'active'],
        start_time__lt=end_time,
        end_time__gt=start_time
    ).values_list('parking_place_id', flat=True)
    # Prefer places within the user's company if available
    company = getattr(user, 'company', None)

    # If a specific parking_place was requested, validate it
    if parking_place:
        # ensure it's not occupied and not in conflicting bookings
        if parking_place.is_occupied or parking_place.id in conflicting_bookings:
            raise ValidationError("Requested parking place is not available for the selected time slot.")
        if company and parking_place.company != company:
            raise ValidationError("Requested parking place does not belong to your company.")
        place_to_book = parking_place
    else:
        place_query = ParkingPlace.objects.exclude(
            id__in=conflicting_bookings
        ).filter(is_occupied=False)
        if company:
            place_query = place_query.filter(company=company)
        place_to_book = place_query.order_by('floor', 'number').first()

        if not place_to_book:
            raise ValidationError("No available places for the selected time slot. Please try another time.")

    # 3. Calculate estimated price
    duration = end_time - start_time
    hours = max(1, math.ceil(duration.total_seconds() / 3600.0))
    
    tariff = Tariff.objects.filter(place_type=place_to_book.place_type, is_active=True).first()
    if not tariff: # Fallback to standard
        tariff = Tariff.objects.filter(place_type='standard', is_active=True).first()
    
    if hours <= 1:
        price = tariff.base_rate if tariff else Decimal('2.00')
    else:
        base = tariff.base_rate if tariff else Decimal('2.00')
        hourly = tariff.hourly_rate if tariff else Decimal('1.50')
        price = base + Decimal(hours - 1) * hourly
    
    days = max(1, math.ceil(duration.total_seconds() / 86400.0))
    daily_max = tariff.daily_max if tariff else Decimal('20.00')
    estimated_price = min(price, daily_max * days)

    # 4. Create the booking instance
    booking = Booking.objects.create(
        user=user, vehicle=vehicle, start_time=start_time, end_time=end_time,
        parking_place=place_to_book, estimated_price=estimated_price
    )

    # 5. Generate QR code
    generate_booking_qr_code(booking)
    return booking


@transaction.atomic
def close_session(session_id):
    """Ends a session, calculates duration/pricing, and frees the parking place."""
    try:
        session = ParkingSession.objects.select_related('vehicle', 'parking_place').get(id=session_id, is_active=True)
    except ParkingSession.DoesNotExist:
        raise ValidationError("Active session not found.")

    session.exit_time = timezone.now()
    session.is_active = False

    # Free for subscription holders
    if session.is_subscription_session:
        session.total_price = Decimal('0.00')
    else:
        # Get tariff for place type
        place_type = session.parking_place.place_type if session.parking_place else 'standard'
        tariff = Tariff.objects.filter(place_type=place_type, is_active=True).first()
        session.total_price = calculate_price(session, tariff)

    if session.parking_place:
        session.parking_place.is_occupied = False
        session.parking_place.save()

    session.save()
    check_and_create_alerts()
    return session
