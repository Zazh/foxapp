from django.urls import path
from . import views

urlpatterns = [
    path('generate/', views.GenerateQRTokenView.as_view(), name='visit-generate-qr'),
    path('generate-guest/', views.GenerateGuestTokenView.as_view(), name='visit-generate-guest'),
    path('scan/', views.ScanQRView.as_view(), name='visit-scan'),
    path('scan/page/', views.ScanPageView.as_view(), name='visit-scan-page'),
    path('history/', views.VisitHistoryView.as_view(), name='visit-history'),
]