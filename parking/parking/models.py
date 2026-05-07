from django.db import models
from django.conf import settings

class ParkingPlace(models.Model):
    number = models.CharField(max_length=10, unique=True)
    floor = models.IntegerField()
    is_occupied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['floor', 'number']

    def __str__(self):
        return f"Place {self.number} (Floor {self.floor})"

class Vehicle(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vehicles'
    )
    plate_number = models.CharField(max_length=20, unique=True)
    brand = models.CharField(max_length=50)
    color = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.plate_number} - {self.brand}"

class ParkingSession(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='sessions')
    parking_place = models.ForeignKey(ParkingPlace, on_delete=models.SET_NULL, null=True, related_name='sessions')
    entry_time = models.DateTimeField(auto_now_add=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    total_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)

    class Meta:
        ordering = ['-entry_time']

    def __str__(self):
        return f"Session: {self.vehicle.plate_number} at {self.parking_place.number if self.parking_place else 'Unknown'}"