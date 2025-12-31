from django.urls import path
from . import views

urlpatterns = [
    path('submit/', views.FeedbackSubmitView.as_view(), name='feedback_submit'),
]