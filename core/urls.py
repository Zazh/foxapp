from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf.urls.i18n import i18n_patterns
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.conf.urls.static import static



# Защищённый TemplateView
class ProtectedTemplateView(LoginRequiredMixin, TemplateView):
    pass


# URL без языкового префикса
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
]

# URL с языковым префиксом
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),

    # Auth (accounts app)
    path('', include('accounts.urls')),
    path('auth/', include('accounts.urls')),

    # Services (services app)
    path('services/', include('services.urls')),

    # Bookings (bookings app)
    path('booking/', include('bookings.urls')),

    # Dashboard (dashboard app)
    path('cabinet/', include('dashboard.urls')),

    # Visits
    path('visit/', include('visits.urls')),

    # Feedback
    path('feedback/', include('feedback.urls')),

    # Backoffice (backoffice app)
    path('backoffice/', include('backoffice.urls', namespace='backoffice')),

    # Public
    path('', TemplateView.as_view(template_name='public/content/home.html'), name='home'),
    path('about/', TemplateView.as_view(template_name='public/content/about.html'), name='about'),
    path('tarif-detail/', TemplateView.as_view(template_name='public/content/tariff_detail.html'), name='tarif_detail'),
    path('contacts/', TemplateView.as_view(template_name='public/content/contacts.html'), name='contacts'),

    # Backoffice (тоже защищённый)
    path('backoffice/', ProtectedTemplateView.as_view(template_name='backoffice/dashboard/cabinet.html'), name='backoffice_dashboard'),

    prefix_default_language=False,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)