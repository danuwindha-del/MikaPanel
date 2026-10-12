from django import forms
from django.contrib.auth.models import User
from .models import Account, Plan
from .validation import domain_name
import ipaddress
from django.contrib.auth.password_validation import validate_password
from .models import DNSRecord, BlockedIP
from .dns import normalize


class ManualAccountForm(forms.ModelForm):
    days = forms.IntegerField(min_value=1, max_value=366, initial=7, label="Masa aktif (hari)",
                              help_text="1–366 hari. Akun ditangguhkan otomatis setelah masa aktif habis.")

    class Meta:
        model = Account
        fields = ["domain", "owner", "plan", "kind"]
        labels = {"domain": "Domain website", "owner": "Pemilik akun", "plan": "Paket hosting", "kind": "Jenis website"}
        widgets = {"domain": forms.TextInput(attrs={"placeholder": "test.mychahost.my.id"})}
        help_texts = {"owner": "Untuk pengujian sendiri, pilih akun admin Anda. Pemilik harus memiliki akun MikaPanels."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["plan"].queryset = Plan.objects.filter(active=True).order_by("disk_mb", "name")

    def clean_domain(self):
        return domain_name(self.cleaned_data["domain"])


class DNSForm(forms.ModelForm):
    class Meta:
        model = DNSRecord
        fields = ["kind", "name", "value", "ttl", "priority"]
        labels = {"kind": "Tipe record", "name": "Nama / host", "value": "Nilai / tujuan", "ttl": "TTL (detik)", "priority": "Prioritas MX"}
        widgets = {"value": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"name": "Gunakan @ untuk domain utama, www untuk alias, atau nama subdomain.", "priority": "Hanya diperlukan untuk MX."}

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.account = account

    def clean(self):
        values = super().clean()
        if all(field in values for field in ["kind", "name", "value", "ttl"]):
            for field in ["kind", "name", "value", "ttl", "priority"]:
                setattr(self.instance, field, values.get(field))
            normalize(self.instance)
            values.update(name=self.instance.name, value=self.instance.value, priority=self.instance.priority)
        return values


class DatabaseForm(forms.Form):
    label = forms.RegexField(regex=r"^[a-z][a-z0-9_]{0,23}$", max_length=24, label="Nama database", help_text="Huruf kecil, angka, underscore; awali dengan huruf.")
    password = forms.CharField(widget=forms.PasswordInput, min_length=12, max_length=128, strip=False, label="Password database")

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        if any(ord(c) < 32 for c in password):
            raise forms.ValidationError("Password tidak boleh berisi karakter kontrol.")
        return password


class DatabasePasswordForm(DatabaseForm):
    label = None


class SecurityForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["force_https", "directory_listing", "security_headers"]
        labels = {"force_https": "Alihkan HTTP ke HTTPS", "directory_listing": "Izinkan daftar isi direktori", "security_headers": "Aktifkan header keamanan"}

    def clean_force_https(self):
        value = self.cleaned_data["force_https"]
        if value and not self.instance.ssl_enabled:
            raise forms.ValidationError("Pasang sertifikat SSL terlebih dahulu sebelum mengaktifkan redirect HTTPS.")
        return value


class BlockIPForm(forms.ModelForm):
    class Meta:
        model = BlockedIP
        fields = ["network", "note"]
        labels = {"network": "IP / jaringan CIDR", "note": "Catatan"}

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.account = account

    def clean_network(self):
        try:
            return str(ipaddress.ip_network(self.cleaned_data["network"].strip(), strict=False))
        except ValueError:
            raise forms.ValidationError("Alamat IP atau CIDR tidak valid.")
