from django import forms
from django.contrib.auth.models import User
from .models import Account, Plan
from .validation import domain_name


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
