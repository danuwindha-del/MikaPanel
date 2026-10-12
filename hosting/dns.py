import ipaddress
import re
import subprocess
import os
import tempfile
import time
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from .models import Account, DNSRecord, ProvisionJob
from .dns_wire import query, zone_ready


class DNSPublishError(RuntimeError):
    pass


def atomic_write(path, text):
    fd, temporary = tempfile.mkstemp(prefix=".mika-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def bind_command(*args):
    return subprocess.run(list(args), check=True, capture_output=True, text=True, timeout=20)


def verify_loaded(account):
    deadline = time.monotonic() + 6
    while True:
        try:
            bind_command("rndc", "zonestatus", account.domain)
            for tcp in [False, True]:
                response = query("127.0.0.1", account.domain, port=getattr(settings, "MIKA_DNS_PORT", 53), tcp=tcp, timeout=1)
                if not zone_ready(response, account.domain, account.dns_serial, hostname(settings.MIKA_DNS_PRIMARY)):
                    raise DNSPublishError("Zone belum memberikan SOA authoritative dengan serial terbaru")
            return
        except (OSError, ValueError, subprocess.SubprocessError, DNSPublishError) as exc:
            if time.monotonic() >= deadline:
                raise DNSPublishError("BIND belum melayani zone melalui UDP dan TCP; periksa named dan port 53") from exc
            time.sleep(.2)


def hostname(value):
    value = str(value).strip().rstrip(".").lower()
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValidationError("Hostname DNS tidak valid.")
    if len(value) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s) for s in value.split(".")):
        raise ValidationError("Hostname DNS tidak valid.")
    return value


def normalize(record):
    name = record.name.strip().lower()
    if name != "@":
        if name.startswith("*."):
            name = "*." + hostname(name[2:])
        elif name != "*":
            if len(name) > 253 or any(not re.fullmatch(r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?", label) for label in name.split(".")):
                raise ValidationError("Nama record DNS tidak valid.")
    if len((name + "." if name != "@" else "") + record.account.domain) > 253:
        raise ValidationError("Nama DNS terlalu panjang.")
    value = record.value.strip()
    if record.kind == "A":
        try:
            value = str(ipaddress.IPv4Address(value))
        except ValueError:
            raise ValidationError("Nilai A harus alamat IPv4.")
    elif record.kind == "AAAA":
        try:
            value = str(ipaddress.IPv6Address(value))
        except ValueError:
            raise ValidationError("Nilai AAAA harus alamat IPv6.")
    elif record.kind in {"CNAME", "MX"}:
        value = hostname(value) + "."
        if record.kind == "CNAME" and name == "@":
            raise ValidationError("CNAME tidak boleh memakai @ karena apex memiliki SOA/NS.")
    elif record.kind == "TXT":
        if not value or len(value.encode()) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValidationError("TXT maksimal 2048 byte dan tidak boleh berisi karakter kontrol.")
    else:
        raise ValidationError("Jenis record tidak didukung.")
    if not 60 <= record.ttl <= 604800:
        raise ValidationError("TTL harus 60–604800 detik.")
    if record.kind == "MX" and (record.priority is None or not 0 <= record.priority <= 65535):
        raise ValidationError("Prioritas MX harus 0–65535.")
    if record.kind != "MX":
        record.priority = None
    conflicts = DNSRecord.objects.filter(account=record.account, name=name).exclude(pk=record.pk)
    if (record.kind == "CNAME" and conflicts.exists()) or conflicts.filter(kind="CNAME").exists():
        raise ValidationError("CNAME tidak dapat digabung dengan record lain pada host yang sama.")
    record.name, record.value = name, value
    return record


@transaction.atomic
def ensure_records(account):
    if Account.objects.filter(pk=account.pk, dns_initialized=False).update(dns_initialized=True):
        DNSRecord.objects.get_or_create(account=account, kind="A", name="@", value=str(ipaddress.IPv4Address(settings.MIKA_SERVER_IP)), defaults={"ttl": 3600})
        DNSRecord.objects.get_or_create(account=account, kind="CNAME", name="www", value=account.domain + ".", defaults={"ttl": 3600})
    account.dns_initialized = True


@transaction.atomic
def enqueue_sync(account):
    Account.objects.filter(pk=account.pk).update(dns_serial=F("dns_serial") + 1, dns_state="pending")
    if not account.jobs.filter(action="dns", state="pending").exists():
        ProvisionJob.objects.create(account=account, action="dns")


def txt_chunks(value):
    raw = value.encode("utf-8")
    def escape(chunk):
        return '"' + "".join(chr(n) if 32 <= n <= 126 and n not in (34, 92) else f"\\{n:03d}" for n in chunk) + '"'
    return " ".join(escape(raw[i:i + 200]) for i in range(0, len(raw), 200))


def render_zone(account, records=None):
    from .validation import domain_name
    domain = domain_name(account.domain)
    primary, secondary = hostname(settings.MIKA_DNS_PRIMARY), hostname(settings.MIKA_DNS_SECONDARY)
    lines = [f"$ORIGIN {domain}.", "$TTL 3600", f"@ IN SOA {primary}. hostmaster.{domain}. ({account.dns_serial} 3600 900 1209600 300)",
             f"@ IN NS {primary}.", f"@ IN NS {secondary}."]
    for record in (records if records is not None else account.dns_records.all()):
        normalize(record)
        value = txt_chunks(record.value) if record.kind == "TXT" else record.value
        if record.kind == "MX":
            value = f"{record.priority} {value}"
        lines.append(f"{record.name} {record.ttl} IN {record.kind} {value}")
    return "\n".join(lines) + "\n"


def publish(account):
    ensure_records(account)
    account.refresh_from_db()
    if settings.MIKA_PROVISION_MODE == "demo":
        target = settings.DATA_DIR / "dns"
        target.mkdir(exist_ok=True)
        (target / f"{account.system_user}.zone").write_text(render_zone(account))
        Account.objects.filter(pk=account.pk).update(dns_state="demo")
        return
    if not settings.MIKA_DNS_ENABLED:
        raise ValueError("DNS service is disabled")
    target_dir = settings.MIKA_BIND_DIR / "mika-zones"
    target_dir.mkdir(mode=0o755, exist_ok=True)
    target_dir.chmod(0o755)
    target = target_dir / f"{account.system_user}.zone"
    previous = target.read_text() if target.exists() else None
    include = settings.MIKA_BIND_DIR / "mika-zones.conf"
    previous_include = include.read_text() if include.exists() else None
    atomic_write(target, render_zone(account))
    try:
        bind_command("named-checkzone", account.domain, str(target))
        zones = []
        for item in Account.objects.order_by("domain"):
            zone = target_dir / f"{item.system_user}.zone"
            if zone.exists():
                from .validation import domain_name
                zones.append(f'zone "{domain_name(item.domain)}" {{ type primary; file "{zone}"; }};')
        atomic_write(include, "\n".join(zones) + "\n")
        bind_command("named-checkconf", "-z")
        configured = bind_command("named-checkconf", "-l")
        if not any(line.split() and line.split()[0].rstrip(".") == account.domain for line in configured.stdout.splitlines()):
            raise DNSPublishError("Zone tidak ada pada konfigurasi BIND aktif; include mika-zones.conf belum terhubung")
        bind_command("rndc", "reconfig")
        bind_command("rndc", "reload", account.domain)
        verify_loaded(account)
    except Exception:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            atomic_write(target, previous)
        if previous_include is None:
            include.unlink(missing_ok=True)
        else:
            atomic_write(include, previous_include)
        try:
            bind_command("rndc", "reconfig")
            if previous is not None:
                bind_command("rndc", "reload", account.domain)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            pass
        raise
    Account.objects.filter(pk=account.pk, dns_serial=account.dns_serial).update(dns_state="published")
