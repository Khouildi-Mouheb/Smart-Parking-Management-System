from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/parking/', include('parking.app_urls')),
    # Include users urls down the line here as well
]