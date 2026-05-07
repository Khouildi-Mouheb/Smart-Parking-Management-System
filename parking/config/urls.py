from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from parking.views import dashboard_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/parking/', include('parking.app_urls')),
    path('', dashboard_view, name='dashboard'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
