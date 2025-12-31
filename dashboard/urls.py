from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardHomeView.as_view(), name='cabinet-dashboard'),
    path('history/', views.DashboardHistoryView.as_view(), name='cabinet-history'),
    path('billing/', views.DashboardBillingView.as_view(), name='cabinet-billing'),
    path('settings/', views.DashboardSettingsView.as_view(), name='cabinet-settings'),
    path('settings/change-password/', views.ChangePasswordView.as_view(), name='cabinet-change-password'),
    path('settings/deactivate/', views.DeactivateAccountView.as_view(), name='cabinet-deactivate'),
    path('booking/<int:pk>/', views.BookingDetailView.as_view(), name='cabinet-booking-detail'),
    path('booking/<int:pk>/extend/', views.ExtendBookingView.as_view(), name='cabinet-booking-extend'),
]