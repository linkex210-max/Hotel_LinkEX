from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from ninja import NinjaAPI

from apps.users.api import router as users_router
from apps.properties.api import router as properties_router
from apps.bookings.api import router as bookings_router
from apps.finance.api import router as finance_router
from apps.notifications.api import router as notifications_router

api = NinjaAPI(
    title="Hotel LinkEX API",
    version="1.0.0",
    description="نظام إدارة وحجوزات الفنادق والوحدات السكنية - Hotel LinkEX Backend API",
    docs_url="/docs",  # Swagger Docs at /api/docs
)

# Register app routers
api.add_router("/users/", users_router, tags=["Users & Auth"])
api.add_router("/properties/", properties_router, tags=["Properties & Units"])
api.add_router("/bookings/", bookings_router, tags=["Bookings & Engine"])
api.add_router("/finance/", finance_router, tags=["Finance & Settlements"])
api.add_router("/notifications/", notifications_router, tags=["Notifications & Celery"])

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
