import math
import qrcode
from io import BytesIO
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.core.files.base import ContentFile
from rest_framework.exceptions import ValidationError
from parking.models import ParkingPlace, ParkingSession, Vehicle

def assign_free_place():
    """Finds and returns the first available parking place."""
    return ParkingPlace.objects.filter(is_occupied=False).order_by('floor', 'number').first()

@transaction.atomic
def create_entry_session(vehicle):
    """Assigns a parking place to a vehicle and opens a session."""
    if ParkingSession.objects.filter(vehicle=vehicle, is_active=True).exists():
        raise ValidationError("This vehicle already has an active parking session.")

    place = assign_free_place()
    if not place:
        raise ValidationError("No parking places available.")

    # Mark place as occupied
    place.is_occupied = True
    place.save()

    # Create and return active session
    session = ParkingSession.objects.create(
        vehicle=vehicle,
        parking_place=place,
        is_active=True
    )

    # Génération du QR Code
    qr_data = f"Session: {session.id} | Plaque: {vehicle.plate_number} | Place: {place.number} (Etage {place.floor}) | Entree: {session.entry_time.strftime('%Y-%m-%d %H:%M')}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    session.qr_code.save(f"session_{session.id}_qr.png", ContentFile(buffer.getvalue()), save=True)

    return session

@transaction.atomic
def close_session(session_id):
    """Ends a session, calculates duration/pricing, and frees the parking place."""
    try:
        # NOTE: select_for_update() is standard here for concurrency, but omitted for SQLite compatibility
        session = ParkingSession.objects.get(id=session_id, is_active=True)
    except ParkingSession.DoesNotExist:
        raise ValidationError("Active session not found.")

    session.exit_time = timezone.now()
    session.is_active = False

    # Calculate pricing based on hours
    duration = session.exit_time - session.entry_time
    hours = max(1, math.ceil(duration.total_seconds() / 3600.0)) # At least 1 hour
    session.total_price = Decimal('2.00') if hours <= 1 else Decimal('2.00') + Decimal(hours - 1) * Decimal('1.00')

    # Free up the parking place
    if session.parking_place:
        session.parking_place.is_occupied = False
        session.parking_place.save()

    session.save()
    return session