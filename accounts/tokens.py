from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Токен для подтверждения email"""
    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{timestamp}{user.is_verified}"


class PasswordResetToken(PasswordResetTokenGenerator):
    """Токен для сброса пароля"""
    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{timestamp}{user.password}"


email_verification_token = EmailVerificationTokenGenerator()
password_reset_token = PasswordResetToken()