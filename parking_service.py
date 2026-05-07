import math
from django.utils import timezone
from django.db import transaction
from rest_framework.exceptions import ValidationError
from ..models import ParkingPlace, ParkingSession, Vehicle

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
    session.total_price = 2.00 if hours <= 1 else 2.00 + (hours - 1) * 1.00

    # Free up the parking place
    if session.parking_place:
        session.parking_place.is_occupied = False
        session.parking_place.save()

    session.save()
    return session