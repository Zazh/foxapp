from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class RegisterForm(forms.Form):
    """Форма регистрации"""
    first_name = forms.CharField(
        label=_('Full Name'),
        max_length=150,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'given-name',
        })
    )
    last_name = forms.CharField(
        label=_('Last Name'),
        max_length=150,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'family-name',
        })
    )
    id_card = forms.CharField(
        label=_('ID Card'),
        max_length=50,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
        })
    )
    phone = forms.CharField(
        label=_('Phone'),
        max_length=20,
        widget=forms.TextInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'tel',
        })
    )
    email = forms.EmailField(
        label=_('Email'),
        widget=forms.EmailInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'new-password',
        })
    )
    password_confirm = forms.CharField(
        label=_('Confirm password'),
        widget=forms.PasswordInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'new-password',
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_('A user with this email already exists.'))
        return email

    def clean_id_card(self):
        id_card = self.cleaned_data.get('id_card', '').strip()
        if User.objects.filter(id_card=id_card).exists():
            raise forms.ValidationError(_('A user with this ID card already exists.'))
        return id_card

    def clean_password(self):
        password = self.cleaned_data.get('password')
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', _('Passwords do not match.'))

        return cleaned_data

    def save(self):
        user = User.objects.create_user(
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            id_card=self.cleaned_data['id_card'],
            phone=self.cleaned_data['phone'],
        )
        return user


class LoginForm(forms.Form):
    """Форма входа"""
    email = forms.EmailField(
        label=_('Email'),
        widget=forms.EmailInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'current-password',
        })
    )
    remember_me = forms.BooleanField(
        label=_('Remember me'),
        required=False,
        initial=True,
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email', '').lower()
        password = cleaned_data.get('password')

        if email and password:
            self.user = authenticate(self.request, email=email, password=password)
            if self.user is None:
                raise forms.ValidationError(_('Invalid email or password.'))
            if not self.user.is_active:
                raise forms.ValidationError(_('This account is inactive.'))

        return cleaned_data

    def get_user(self):
        return self.user


class ForgotPasswordForm(forms.Form):
    """Форма запроса сброса пароля"""
    email = forms.EmailField(
        label=_('Email'),
        widget=forms.EmailInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'email',
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        return email

    def get_user(self):
        email = self.cleaned_data.get('email')
        try:
            return User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return None


class ResetPasswordForm(forms.Form):
    """Форма установки нового пароля"""
    password = forms.CharField(
        label=_('New password'),
        widget=forms.PasswordInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'new-password',
        })
    )
    password_confirm = forms.CharField(
        label=_('Confirm new password'),
        widget=forms.PasswordInput(attrs={
            'placeholder': ' ',
            'autocomplete': 'new-password',
        })
    )

    def clean_password(self):
        password = self.cleaned_data.get('password')
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', _('Passwords do not match.'))

        return cleaned_data