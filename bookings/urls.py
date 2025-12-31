from django.urls import path
from . import views

urlpatterns = [
    path(
        '<str:service_type>/<slug:slug>/book/',
        views.BookingCreateView.as_view(),
        name='booking_create'
    ),
    path(
        'mock-payment/<int:pk>/',
        views.BookingMockPaymentView.as_view(),
        name='booking_mock_payment'
    ),
    path(
        'success/<int:pk>/',
        views.BookingSuccessView.as_view(),
        name='booking_success'
    ),
    path(
        'cancel/<int:pk>/',
        views.BookingCancelView.as_view(),
        name='booking_cancel'
    ),
    path(
        'webhook/stripe/',
        views.StripeWebhookView.as_view(),
        name='stripe_webhook'
    ),
]