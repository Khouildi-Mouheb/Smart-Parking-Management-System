from django.db import models
from django.conf import settings
from django.utils import timezone


class ParkingPlace(models.Model):
    PLACE_TYPES = (
        ('standard', 'Standard'),
        ('handicapped', 'Handicapped'),
        ('vip', 'VIP'),
        ('electric', 'Electric Vehicle'),
    )

    number = models.CharField(max_length=10, unique=True)
    floor = models.IntegerField()
    place_type = models.CharField(max_length=20, choices=PLACE_TYPES, default='standard')
    is_occupied = models.BooleanField(default=False)
    is_reserved = models.BooleanField(default=False)
    hourly_rate = models.DecimalField(max_digits=6, decimal_places=2, default=2.00)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['floor', 'number']

    def __str__(self):
        return f"Place {self.number} (Floor {self.floor}) [{self.place_type}]"

    @property
    def status(self):
        if self.is_occupied:
            return 'occupied'
        if self.is_reserved:
            return 'reserved'
        return 'free'


class Vehicle(models.Model):
    VEHICLE_TYPES = (
        ('car', 'Car'),
        ('motorcycle', 'Motorcycle'),
        ('truck', 'Truck'),
        ('electric', 'Electric Vehicle'),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vehicles'
    )
    plate_number = models.CharField(max_length=20, unique=True)
    brand = models.CharField(max_length=50)
    model = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=30)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES, default='car')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.plate_number} - {self.brand} {self.model}"


class Subscription(models.Model):
    PLAN_CHOICES = (
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    )
    PLAN_PRICES = {
        'daily': 15.00,
        'weekly': 70.00,
        'monthly': 250.00,
        'annual': 2500.00,
    }

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    start_date = models.DateField()
    end_date = models.DateField()
    auto_renew = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.plan} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.price:
            self.price = self.PLAN_PRICES.get(self.plan, 0)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return self.status == 'active' and self.end_date >= timezone.now().date()

    @property
    def days_remaining(self):
        if self.is_valid:
            return (self.end_date - timezone.now().date()).days
        return 0


class ParkingSession(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='sessions')
    parking_place = models.ForeignKey(ParkingPlace, on_delete=models.SET_NULL, null=True, related_name='sessions')
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_sessions')
    entry_time = models.DateTimeField(auto_now_add=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    total_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_subscription_session = models.BooleanField(default=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-entry_time']

    def __str__(self):
        return f"Session: {self.vehicle.plate_number} at {self.parking_place.number if self.parking_place else 'Unknown'}"

    @property
    def duration_minutes(self):
        end = self.exit_time or timezone.now()
        return int((end - self.entry_time).total_seconds() / 60)

    @property
    def duration_display(self):
        mins = self.duration_minutes
        hours = mins // 60
        remaining = mins % 60
        if hours > 0:
            return f"{hours}h {remaining}m"
        return f"{remaining}m"


class ParkingAlert(models.Model):
    ALERT_TYPES = (
        ('place_available', 'Place Available'),
        ('almost_full', 'Parking Almost Full'),
        ('full', 'Parking Full'),
        ('subscription_expiry', 'Subscription Expiring'),
        ('overstay', 'Vehicle Overstay'),
    )
    SEVERITY = (
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    )

    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY, default='info')
    message = models.TextField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity}] {self.alert_type}: {self.message[:50]}"


class Tariff(models.Model):
    name = models.CharField(max_length=100)
    place_type = models.CharField(max_length=20, choices=ParkingPlace.PLACE_TYPES, default='standard')
    base_rate = models.DecimalField(max_digits=6, decimal_places=2, default=2.00)
    hourly_rate = models.DecimalField(max_digits=6, decimal_places=2, default=1.50)
    daily_max = models.DecimalField(max_digits=6, decimal_places=2, default=20.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.place_type}"
