from django.urls import path
from . import views
from .views import (
    register_view, register_done_view, verify_email_view,
    login_view, logout_view,
    forgot_password_view, forgot_password_done_view, reset_password_view,
    telegram_generate_link, telegram_webhook, telegram_disconnect
)

urlpatterns = [
    path('register/', register_view, name='register'),
    path('register/done/', register_done_view, name='register_done'),
    path('verify/<uidb64>/<token>/', verify_email_view, name='verify_email'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('forgot-password/', forgot_password_view, name='forgot_password'),
    path('forgot-password/done/', forgot_password_done_view, name='forgot_password_done'),
    path('reset-password/<uidb64>/<token>/', reset_password_view, name='reset_password'),

    # Telegram
    path('telegram/generate-link/', telegram_generate_link, name='telegram_generate_link'),
    path('telegram/webhook/', telegram_webhook, name='telegram_webhook'),
    path('telegram/disconnect/', telegram_disconnect, name='telegram_disconnect'),

]