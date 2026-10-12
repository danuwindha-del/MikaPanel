import ipaddress
import re
from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import ValidationError


def domain_name(value):
    value = str(value).strip().lower()
    if value.startswith("www."):
        raise ValidationError("Masukkan domain utama tanpa www; alias www disiapkan otomatis.")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValidationError("Domain tidak valid.")
    if len(value) > 253 or "." not in value:
        raise ValidationError("Gunakan domain lengkap, misalnya bisnisanda.com.")
    parts = value.split(".")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s) for s in parts):
        raise ValidationError("Domain tidak valid.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValidationError("Masukkan nama domain, bukan alamat IP.")
    if not re.fullmatch(r"[a-z]{2,63}|xn--[a-z0-9-]+", parts[-1]):
        raise ValidationError("Ekstensi domain tidak valid.")
    reserved = {urlsplit(settings.MIKA_PANEL_URL).hostname, urlsplit(settings.MYCHA_PUBLIC_URL).hostname}
    if {value, "www." + value} & reserved:
        raise ValidationError("Domain panel dan toko tidak dapat digunakan untuk akun hosting.")
    return value
