from django.urls import path
from . import views

urlpatterns = [
    path('<slug:slug>/', views.PolicyDetailView.as_view(), name='policy_detail'),
]
