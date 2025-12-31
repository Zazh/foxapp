from django.urls import path
from . import views

urlpatterns = [
    path('<str:service_type>/', views.ServiceDetailView.as_view(), name='service_detail'),
    path('<str:service_type>/<slug:slug>/', views.TariffDetailView.as_view(), name='tariff_detail'),
]