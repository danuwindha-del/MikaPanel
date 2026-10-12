import io
import os
import zipfile
from datetime import timedelta
from unittest.mock import patch
import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from common.models import Notification
from hosting import dns, files
from hosting.databases import decrypt_password, provision
from hosting.models import AccountUsage, BlockedIP, DNSRecord, ManagedDatabase, MetricSample, ProvisionJob
from hosting.provisioner import nginx_config, process
from hosting.telemetry import collect_account, collect_server

pytestmark = pytest.mark.django_db


@pytest.fixture
def active(panel, account):
    process(account, "create")
    account.status = "active"
    account.save(update_fields=["status"])
    return account


def test_nested_files_backup_and_rename(active):
    files.create_directory(active, "assets")
    files.write_file(active, "assets/style.css", b"body{color:gold}")
    files.write_file(active, ".htaccess", b"# Nginx does not read this")
    assert files.listing(active)[0]["is_dir"]
    files.rename(active, "assets/style.css", "main.css")
    assert files.read_file(active, "assets/main.css") == b"body{color:gold}"
    with pytest.raises(OSError):
        files.rename(active, "assets/main.css", "main.css")
    with zipfile.ZipFile(files.backup_zip(active)) as archive:
        assert archive.read("assets/main.css") == b"body{color:gold}"
        assert ".htaccess" in archive.namelist()
    with pytest.raises(OSError):
        files.delete(active, "assets")
    files.delete(active, "assets/main.css")
    files.delete(active, "assets")


def archive_bytes(path, data=b"bad"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(path, data)
    return output.getvalue()


@pytest.mark.parametrize("name", ["../escape.php", "/escape.php", "assets/../../escape.php", "a\\b.php", "./x.php"])
def test_zip_traversal_rejected_before_writes(active, name):
    with pytest.raises(ValueError):
        files.extract_zip(active, archive_bytes(name))
    assert [e["name"] for e in files.listing(active)] == ["index.html"]


def test_zip_nested_extract_and_symlink_hardlink_protection(active, tmp_path):
    files.extract_zip(active, archive_bytes("assets/app.js", b"const x=1"))
    assert files.read_file(active, "assets/app.js") == b"const x=1"
    secret = tmp_path / "outside.txt"
    secret.write_text("outside")
    (files.public_path(active) / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        files.read_file(active, "link/outside.txt")
    os.link(secret, files.public_path(active) / "hard.txt")
    with pytest.raises(ValueError):
        files.read_file(active, "hard.txt")
    with pytest.raises(ValueError):
        files.write_file(active, "hard.txt", b"overwrite")
    assert secret.read_text() == "outside"


def test_quota_includes_subfolders(active):
    active.plan.disk_mb = 1
    active.plan.save()
    files.create_directory(active, "assets")
    files.write_file(active, "assets/large.bin", b"x" * 900000)
    with pytest.raises(ValueError, match="penyimpanan"):
        files.write_file(active, "other.bin", b"x" * 200000)


def test_dns_crud_conflicts_ttl_owner_and_serial(client, user, active):
    client.force_login(user)
    url = f"/accounts/{active.pk}/dns/"
    before = active.dns_serial
    response = client.post(url, {"kind": "TXT", "name": "_dmarc", "value": 'v=DMARC1; p=none', "ttl": 3600})
    assert response.status_code == 302
    record = active.dns_records.get(name="_dmarc")
    active.refresh_from_db()
    assert active.dns_serial == before + 1
    response = client.post(url + f"?edit={record.pk}", {"kind": "TXT", "name": "_dmarc", "value": "v=DMARC1; p=reject", "ttl": 60})
    assert response.status_code == 302
    record.refresh_from_db()
    assert record.value.endswith("reject")
    response = client.post(url, {"kind": "A", "name": "www", "value": "172.236.9.185", "ttl": 3600})
    assert response.status_code == 200
    assert "CNAME" in response.content.decode()
    assert not active.dns_records.filter(name="www", kind="A").exists()
    assert client.get(url + "?edit=garbage").status_code == 404
    assert client.post(f"{url}{record.pk}/delete/").status_code == 302
    assert not DNSRecord.objects.filter(pk=record.pk).exists()
    assert active.jobs.filter(action="dns", state="pending").count() == 1


@pytest.mark.parametrize("kind,name,value,ttl,priority", [
    ("A", "@", "127.0.0.1;include", 3600, None), ("AAAA", "@", "wrong", 3600, None),
    ("TXT", "bad\nowner", "value", 3600, None), ("TXT", "@", 'x\n@ IN A 1.2.3.4', 3600, None),
    ("CNAME", "@", "example.test", 3600, None), ("MX", "mail", "example.test", 3600, None),
    ("A", "@", "1.2.3.4", 59, None),
])
def test_dns_validation_rejects_invalid_zone_input(panel, account, kind, name, value, ttl, priority):
    with pytest.raises(ValidationError):
        dns.normalize(DNSRecord(account=account, kind=kind, name=name, value=value, ttl=ttl, priority=priority))


def test_dns_rollback_and_deleted_default_not_recreated(panel, active, tmp_path):
    active.dns_records.filter(name="www").delete()
    dns.ensure_records(active)
    assert not active.dns_records.filter(name="www").exists()
    panel.MIKA_PROVISION_MODE = "system"
    panel.MIKA_DNS_ENABLED = True
    panel.MIKA_BIND_DIR = tmp_path / "bind"
    directory = panel.MIKA_BIND_DIR / "mika-zones"
    directory.mkdir(parents=True)
    zone = directory / f"{active.system_user}.zone"
    zone.write_text("old zone")
    include = panel.MIKA_BIND_DIR / "mika-zones.conf"
    include.write_text("old include")
    with patch("hosting.dns.subprocess.run", side_effect=RuntimeError("validator failed")):
        with pytest.raises(RuntimeError):
            dns.publish(active)
    assert zone.read_text() == "old zone" and include.read_text() == "old include"


def test_database_queue_encryption_capacity_rotation_delete(client, user, active):
    client.force_login(user)
    active.plan.database_limit = 1
    active.plan.save()
    url = f"/accounts/{active.pk}/databases/"
    password = "Feature-test-database-2048!"
    assert client.post(url, {"label": "wordpress", "password": password}).status_code == 302
    database = active.managed_databases.get()
    assert password not in database.password_ciphertext
    assert decrypt_password(database.password_ciphertext) == password
    call_command("provision_worker", once=True)
    database.refresh_from_db()
    assert database.state == "demo"
    response = client.post(url, {"label": "extra", "password": password})
    assert response.status_code == 200 and active.managed_databases.count() == 1
    action = f"{url}{database.pk}/action/"
    assert client.post(action, {"action": "password", "password": "Rotated-feature-test-4096!"}).status_code == 302
    call_command("provision_worker", once=True)
    database.refresh_from_db()
    assert decrypt_password(database.password_ciphertext) == "Rotated-feature-test-4096!"
    assert client.post(action, {"action": "delete"}).status_code == 302
    call_command("provision_worker", once=True)
    database.refresh_from_db(); active.refresh_from_db()
    assert database.state == "deleted" and not database.password_ciphertext and active.database_count == 0
    provision(database, "db_delete")
    active.refresh_from_db()
    assert active.database_count == 0


def test_feature_ownership_and_csrf(client, user, other, active):
    client.force_login(other)
    for suffix in ["files/manage/", "dns/", "dns/export/", "databases/", "ssl/", "security/", "statistics/"]:
        assert client.get(f"/accounts/{active.pk}/{suffix}").status_code == 404
    for suffix in ["dns/sync/", "ssl/request/", "files/action/"]:
        assert client.post(f"/accounts/{active.pk}/{suffix}").status_code == 404
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(user)
    for suffix in ["dns/", "databases/", "security/", "ssl/request/", "files/action/"]:
        assert csrf.post(f"/accounts/{active.pk}/{suffix}", {}).status_code == 403


def test_security_settings_generate_real_nginx_rules(client, user, active):
    client.force_login(user)
    url = f"/accounts/{active.pk}/security/"
    assert client.post(url, {"action": "block", "network": "203.0.113.99/24", "note": "test"}).status_code == 302
    assert active.blocked_ips.get().network == "203.0.113.0/24"
    assert client.post(url, {"action": "settings", "directory_listing": "on", "security_headers": "on"}).status_code == 302
    active.refresh_from_db()
    config = nginx_config(active)
    assert "deny 203.0.113.0/24;" in config and "autoindex on;" in config and "nosniff" in config
    assert "disable_symlinks on" in config
    response = client.post(url, {"action": "settings", "force_https": "on", "security_headers": "on"})
    assert response.status_code == 200
    active.refresh_from_db()
    assert not active.force_https
    assert active.jobs.filter(action="refresh", state="pending").count() == 1


def test_real_metrics_incremental_log_no_double_count_rotation(panel, active, tmp_path):
    panel.MIKA_NGINX_LOG_DIR = tmp_path / "logs"
    panel.MIKA_NGINX_LOG_DIR.mkdir()
    log = panel.MIKA_NGINX_LOG_DIR / f"mika-site-{active.system_user}.access.log"
    log.write_text("172.2 200 100\n172.3 404 50\n")
    collect_account(active); collect_account(active)
    usage = AccountUsage.objects.get(account=active)
    assert (usage.requests, usage.error_requests, usage.bandwidth_bytes) == (2, 1, 150)
    assert usage.disk_bytes > 0
    log.rename(log.with_suffix(".old"))
    log.write_text("173.0 200 20\n")
    collect_account(active)
    usage.refresh_from_db()
    assert (usage.requests, usage.bandwidth_bytes) == (3, 170)
    sample = collect_server()
    assert sample.memory_total > 0 and sample.disk_total > 0 and sample.cpu_percent is None
    MetricSample.objects.filter(pk=sample.pk).update(created_at=timezone.now() - timedelta(seconds=30), cpu_total=sample.cpu_total - 100, cpu_idle=sample.cpu_idle - 40)
    assert collect_server().cpu_percent is not None


def test_notifications_read_only_own_and_password_keeps_session(client, user, other, panel):
    own = Notification.objects.create(user=user, title="Own", link="/dashboard/")
    alien = Notification.objects.create(user=other, title="Alien")
    client.force_login(user)
    assert b"Own" in client.get("/notifications/").content
    assert b"Alien" not in client.get("/notifications/").content
    client.post("/notifications/")
    own.refresh_from_db(); alien.refresh_from_db()
    assert own.is_read and not alien.is_read
    response = client.post("/profile/", {"action": "password", "old_password": "Long-test-password-2048!",
        "new_password1": "Changed-feature-password-4096!", "new_password2": "Changed-feature-password-4096!"})
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.check_password("Changed-feature-password-4096!")
    assert client.get("/dashboard/").status_code == 200


def test_shop_active_notification_created_once(order):
    from storefront.panel_client import fulfill
    order.status = "paid"; order.save()
    data = {"external_id": order.reference, "domain": order.domain, "id": "fixture-panel-id", "status": "active"}
    with patch("storefront.panel_client.call", return_value=data):
        fulfill(order)
        order.refresh_from_db()
        fulfill(order)
    assert Notification.objects.filter(user=order.user, title="Hosting Anda sudah aktif").count() == 1
