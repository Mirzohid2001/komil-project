# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import verify_certificate

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    # Public QR verification URL used in generated certificate PDFs
    path(
        'verify-certificate/<str:certificate_id>/',
        verify_certificate,
        name='verify_certificate_detail',
    ),
    path('', include('blog.urls', namespace='blog')),
    path('courses/', include('courses.urls', namespace='courses')),
]

if settings.DEBUG:
    # Явно добавляем обработку медиа-файлов в режиме разработки
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
