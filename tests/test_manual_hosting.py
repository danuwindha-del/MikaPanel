from datetime import timedelta
from unittest.mock import patch
import pytest
from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from common.models import AuditEvent
from hosting.files import read_file
from hosting.models import Account, Plan, ProvisionJob
from storefront.models import Order, PaymentEvent


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("manualadmin", "admin@example.test", "Manual-fixture-password-2048!")


def payload(owner, plan, **changes):
    return {"domain": "test.example.test", "owner": owner.pk, "plan": plan.pk, "kind": "static", "days": 7, **changes}


@pytest.mark.django_db
def test_admin_creates_hosting_without_payment_and_worker_activates(client, panel, plan, admin_user):
    client.force_login(admin_user)
    assert b"Buat hosting" in client.get("/dashboard/").content
    response = client.post("/accounts/create/", payload(admin_user, plan))
    assert response.status_code == 302
    account = Account.objects.get()
    assert response.url == f"/accounts/{account.pk}/"
    assert account.status == "queued" and account.external_id.startswith("MANUAL-")
    assert account.owner == admin_user and account.plan == plan
    assert abs((account.expires_at - timezone.now() - timedelta(days=7)).total_seconds()) < 3
    assert ProvisionJob.objects.get().action == "create"
    assert AuditEvent.objects.get().action == "hosting.manual.create"
    assert Order.objects.count() == PaymentEvent.objects.count() == 0
    call_command("provision_worker", once=True)
    account.refresh_from_db()
    assert account.status == "active" and ProvisionJob.objects.get().state == "done"
    assert b"test.example.test" in read_file(account, "index.html")
    assert client.get(f"/accounts/{account.pk}/").status_code == 200


@pytest.mark.django_db
def test_customer_and_staff_without_permission_cannot_create(client, panel, plan, user):
    assert client.get("/accounts/create/").status_code == 302
    client.force_login(user)
    assert b"Buat hosting" not in client.get("/dashboard/").content
    assert client.get("/accounts/create/").status_code == 403
    assert client.post("/accounts/create/", payload(user, plan)).status_code == 403
    user.is_staff = True
    user.save()
    assert client.post("/accounts/create/", payload(user, plan)).status_code == 403
    assert Account.objects.count() == ProvisionJob.objects.count() == 0


@pytest.mark.django_db
def test_staff_with_explicit_add_permission_can_create(client, panel, plan, user):
    user.is_staff = True
    user.save()
    user.user_permissions.add(Permission.objects.get(codename="add_account", content_type__app_label="hosting"))
    client.force_login(user)
    assert client.post("/accounts/create/", payload(user, plan)).status_code == 302
    assert Account.objects.count() == ProvisionJob.objects.count() == 1


@pytest.mark.django_db
def test_duplicate_submission_does_not_duplicate_provisioning(client, panel, plan, admin_user):
    client.force_login(admin_user)
    data = payload(admin_user, plan)
    assert client.post("/accounts/create/", data).status_code == 302
    assert client.post("/accounts/create/", data).status_code == 200
    assert Account.objects.count() == ProvisionJob.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("changes", [{"domain": "bad.com;rm"}, {"domain": "shop.example.test"}, {"domain": "www.example.test"}, {"days": 0}, {"days": 367}, {"kind": "vps"}])
def test_invalid_manual_configuration_is_rejected(client, panel, plan, admin_user, changes):
    client.force_login(admin_user)
    assert client.post("/accounts/create/", payload(admin_user, plan, **changes)).status_code == 200
    assert Account.objects.count() == ProvisionJob.objects.count() == 0


@pytest.mark.django_db
def test_inactive_plan_and_owner_not_accepted(client, panel, plan, admin_user, user):
    client.force_login(admin_user)
    plan.active = False
    plan.save()
    assert client.post("/accounts/create/", payload(admin_user, plan)).status_code == 200
    plan.active = True
    plan.save()
    user.is_active = False
    user.save()
    assert client.post("/accounts/create/", payload(user, plan)).status_code == 200
    assert Account.objects.count() == 0


@pytest.mark.django_db
def test_admin_add_form_uses_same_provisioning_flow(client, panel, plan, admin_user):
    client.force_login(admin_user)
    response = client.get("/admin/hosting/account/add/")
    assert response.status_code == 200 and b'name="days"' in response.content
    response = client.post("/admin/hosting/account/add/", {**payload(admin_user, plan), "_save": "Save"})
    assert response.status_code == 302
    account = Account.objects.get()
    assert account.status == "queued" and account.external_id.startswith("MANUAL-")
    assert account.jobs.count() == 1
    assert AuditEvent.objects.get(action="hosting.manual.create").actor == admin_user.username
    assert Order.objects.count() == 0
    assert client.get(f"/admin/hosting/account/{account.pk}/change/").status_code == 200


@pytest.mark.django_db
def test_manual_creation_requires_csrf(panel, admin_user, plan):
    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    assert client.post("/accounts/create/", payload(admin_user, plan)).status_code == 403
    assert Account.objects.count() == 0


@pytest.mark.django_db
def test_failed_queue_insert_rolls_back_account(client, panel, admin_user, plan):
    client.force_login(admin_user)
    with patch("hosting.services.ProvisionJob.objects.create", side_effect=RuntimeError("Queue unavailable")), pytest.raises(RuntimeError):
        client.post("/accounts/create/", payload(admin_user, plan))
    assert Account.objects.count() == ProvisionJob.objects.count() == 0
    assert not AuditEvent.objects.filter(action="hosting.manual.create").exists()
