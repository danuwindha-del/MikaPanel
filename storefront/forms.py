from django import forms
from hosting.validation import domain_name


class CheckoutForm(forms.Form):
    domain = forms.CharField(max_length=253, label="Domain Anda", widget=forms.TextInput(attrs={"placeholder": "bisnisanda.com"}))
    customer_phone = forms.RegexField(regex=r"^\+?[0-9]{8,16}$", max_length=20, label="Nomor telepon pembayaran", widget=forms.TextInput(attrs={"placeholder": "081234567890"}))
    kind = forms.ChoiceField(choices=[("php", "PHP 8.3"), ("static", "Website statis")], label="Jenis website")
    cycle = forms.TypedChoiceField(choices=[(1, "1 bulan"), (3, "3 bulan"), (12, "12 bulan")], coerce=int, label="Periode berlangganan")
    coupon = forms.CharField(max_length=32, required=False, label="Kode promo (opsional)")
    agree = forms.BooleanField(label="Saya menyetujui ketentuan layanan dan penggunaan hosting.")

    def clean_domain(self):
        return domain_name(self.cleaned_data["domain"])
