import hashlib
import os
from datetime import timedelta
from unittest.mock import patch
import pytest
from django.core.management import call_command
from django.utils import timezone
from hosting import files
from hosting.models import Account, LoginToken, ProvisionJob
from hosting.provisioner import nginx_config, process
from hosting.validation import domain_name
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_api_creates_single_job_on_retries(client, panel, plan):
    payload = {"external_id": "MH-order", "customer_id": "customer-1", "email": "owner@example.test", "plan": "launch", "domain": "site.example.test", "kind": "php", "days": 30}
    auth = {"HTTP_AUTHORIZATION": "Bearer fixture-panel-only"}
    first = client.post("/api/v1/accounts/", payload, content_type="application/json", **auth)
    second = client.post("/api/v1/accounts/", payload, content_type="application/json", **auth)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert Account.objects.count() == ProvisionJob.objects.count() == 1
    payload["domain"] = "other.example.test"
    assert client.post("/api/v1/accounts/", payload, content_type="application/json", **auth).status_code == 409


@pytest.mark.django_db
def test_api_fails_closed_without_token(client, panel):
    assert client.post("/api/v1/accounts/", {}, content_type="application/json").status_code == 401
    panel.MIKA_API_TOKEN = ""
    assert client.post("/api/v1/accounts/", {}, content_type="application/json", HTTP_AUTHORIZATION="Bearer ").status_code == 401


@pytest.mark.django_db
def test_worker_demo_provisions_real_files_and_expiry(panel, account):
    ProvisionJob.objects.create(account=account, action="create")
    call_command("provision_worker", once=True)
    account.refresh_from_db()
    assert account.status == "active"
    assert account.jobs.get().state == "done"
    assert account.domain.encode() in files.read_file(account, "index.html")
    call_command("provision_worker", once=True)
    assert account.jobs.count() == 1
    account.expires_at = timezone.now() - timedelta(seconds=1)
    account.save()
    call_command("provision_worker", once=True)
    account.refresh_from_db()
    assert account.status == "suspended"


@pytest.mark.django_db
def test_worker_records_failure_without_fake_activation(panel, account):
    ProvisionJob.objects.create(account=account, action="create")
    from django.core.management.base import CommandError
    with patch("hosting.management.commands.provision_worker.process", side_effect=PermissionError), pytest.raises(CommandError):
        call_command("provision_worker", once=True)
    account.refresh_from_db()
    assert account.status == "failed" and account.jobs.get().state == "failed"


@pytest.mark.django_db
def test_file_manager_blocks_symlinks_and_traversal(panel, account, tmp_path):
    process(account, "create")
    secret = tmp_path / "outside.txt"
    secret.write_text("private")
    path = files.public_path(account)
    (path / "evil.txt").symlink_to(secret)
    assert "evil.txt" not in [entry["name"] for entry in files.listing(account)]
    with pytest.raises(OSError):
        files.read_file(account, "evil.txt")
    with pytest.raises(OSError):
        files.write_file(account, "evil.txt", b"changed")
    with pytest.raises(ValueError):
        files.read_file(account, "../../outside.txt")
    assert secret.read_text() == "private"


@pytest.mark.django_db
def test_customer_cannot_access_other_site(client, panel, account, other):
    client.force_login(other)
    assert client.get(f"/accounts/{account.pk}/").status_code == 404
    assert client.post(f"/accounts/{account.pk}/files/", {"filename": "index.html", "content": "hack"}).status_code == 404
    assert client.post(f"/accounts/{account.pk}/action/", {"action": "suspend"}).status_code == 403


@pytest.mark.django_db
def test_file_save_and_backup(client, panel, account, user):
    process(account, "create")
    account.status = "active"
    account.save()
    client.force_login(user)
    assert client.post(f"/accounts/{account.pk}/files/", {"filename": "hello.html", "content": "<h1>Hello</h1>"}).status_code == 302
    assert files.read_file(account, "hello.html") == b"<h1>Hello</h1>"
    response = client.get(f"/accounts/{account.pk}/backup/")
    assert response.status_code == 200
    import io, zipfile
    with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as z:
        assert z.read("hello.html") == b"<h1>Hello</h1>"


@pytest.mark.django_db
def test_sso_one_use_origin_and_expiry(client, panel, user):
    token = "fixture-one-use"
    LoginToken.objects.create(digest=hashlib.sha256(token.encode()).hexdigest(), owner=user, expires_at=timezone.now() + timedelta(seconds=60))
    assert client.post("/sso/", {"token": token}, HTTP_ORIGIN="https://evil.example").status_code == 403
    assert client.post("/sso/", {"token": token}, HTTP_ORIGIN=panel.MYCHA_PUBLIC_URL).status_code == 302
    assert client.post("/sso/", {"token": token}, HTTP_ORIGIN=panel.MYCHA_PUBLIC_URL).status_code == 403
    LoginToken.objects.all().update(used=False, expires_at=timezone.now() - timedelta(seconds=1))
    assert client.post("/sso/", {"token": token}, HTTP_ORIGIN=panel.MYCHA_PUBLIC_URL).status_code == 403


@pytest.mark.parametrize("value", ["example.com;rm -rf /", "../example.com", "x\nserver{}", "localhost", "127.0.0.1", "bad..com", "-bad.com", "x.com/path"])
def test_domain_rejects_injection(value):
    with pytest.raises(ValidationError):
        domain_name(value)


def test_domain_normalization():
    assert domain_name("Example.COM") == "example.com"


def test_domain_reserved_and_www_alias(panel):
    panel.MIKA_PANEL_URL = "https://panel.example.com"
    with pytest.raises(ValidationError):
        domain_name("panel.example.com")
    with pytest.raises(ValidationError):
        domain_name("www.customer.example.com")


def test_retry_index_never_follows_existing_symlink(tmp_path):
    from hosting.provisioner import seed_index
    sensitive = tmp_path / "sensitive.txt"
    sensitive.write_text("untouched")
    index = tmp_path / "index.html"
    index.symlink_to(sensitive)
    seed_index(index, "customer.example.com")
    assert index.is_symlink() and sensitive.read_text() == "untouched"
    sensitive.unlink()
    seed_index(index, "customer.example.com")
    assert not sensitive.exists()  # Dangling symlink must not be followed either.


@pytest.mark.django_db
def test_static_files_readable_by_nginx_under_service_umask(panel, account):
    previous = os.umask(0o007)
    try:
        process(account, "create")
        files.write_file(account, "page.html", b"public content")
    finally:
        os.umask(previous)
    for name in ["index.html", "page.html"]:
        assert (files.public_path(account) / name).stat().st_mode & 0o004
        assert files.read_file(account, name)


@pytest.mark.django_db
def test_nginx_php_config_scoped_to_account(panel, account):
    account.kind = "php"
    text = nginx_config(account)
    assert f"server_name {account.domain} www.{account.domain};" in text
    assert f"fastcgi_pass unix:/run/php/{account.system_user}.sock;" in text
    assert "location ~ /\\." in text
    assert "location ^~ /.well-known/acme-challenge/" in text


@pytest.mark.django_db
def test_ssl_unavailable_in_demo_is_not_reported_success(panel, account):
    with pytest.raises(ValueError, match="SSL requires"):
        process(account, "ssl")


@pytest.mark.django_db
def test_resume_preserves_certificate_configuration(panel, account):
    with patch("hosting.provisioner.Path.exists", return_value=True):
        text = nginx_config(account, suspended=True)
    assert "listen 443 ssl;" in text and "return 503;" in text
    assert f"/etc/letsencrypt/live/{account.domain}/fullchain.pem" in text
