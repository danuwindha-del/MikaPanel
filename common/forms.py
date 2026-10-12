from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Ticket


class RegisterForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=80, label="Nama lengkap")

    class Meta:
        model = User
        fields = ["username", "first_name", "email", "password1", "password2"]

    def clean_email(self):
        value = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError("Email sudah digunakan.")
        return value


class TicketForm(forms.ModelForm):
    body = forms.CharField(widget=forms.Textarea, max_length=5000, label="Pesan")

    class Meta:
        model = Ticket
        fields = ["subject", "priority"]
