from django.urls import path
from . import views

app_name = 'backoffice'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),

    # Units (Storage)
    path('units/', views.UnitListView.as_view(), name='unit_list'),
    path('units/<int:pk>/', views.UnitDetailView.as_view(), name='unit_detail'),
    path('units/<int:pk>/toggle/', views.unit_toggle_status, name='unit_toggle'),

    # Bookings (Payments)
    path('bookings/', views.BookingListView.as_view(), name='booking_list'),
    path('bookings/<int:pk>/', views.BookingDetailView.as_view(), name='booking_detail'),
    path('bookings/<int:pk>/release/', views.booking_release, name='booking_release'),

    # Users
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),

    # Visits
    path('visits/', views.VisitListView.as_view(), name='visit_list'),

    # Feedback
    path('feedback/', views.FeedbackListView.as_view(), name='feedback_list'),
    path('feedback/<int:pk>/status/', views.feedback_update_status, name='feedback_update_status'),
    path('feedback/<int:pk>/notes/', views.feedback_update_notes, name='feedback_update_notes'),

    # Scanner
    path('scanner/', views.ScannerView.as_view(), name='scanner'),
]