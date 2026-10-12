"""Manual hosting is a staff operation, separate from customer invoices/payments."""
import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from common.models import AuditEvent
from .models import ProvisionJob
from .validation import domain_name


def can_create_manual_account(user):
    return user.is_authenticated and user.is_staff and user.has_perm("hosting.add_account")


@transaction.atomic
def save_manual_account(account, *, actor, days):
    if not can_create_manual_account(actor):
        raise PermissionError("Hosting creation permission required")
    if not account._state.adding or not 1 <= days <= 366:
        raise ValueError("A new account and valid duration are required")
    account.domain = domain_name(account.domain)
    account.external_id = "MANUAL-" + uuid.uuid4().hex
    account.status = "queued"
    account.expires_at = timezone.now() + timedelta(days=days)
    account.full_clean()
    account.save()
    from .dns import ensure_records
    ensure_records(account)
    ProvisionJob.objects.create(account=account, action="create")
    AuditEvent.objects.create(actor=actor.username, action="hosting.manual.create", target=account.domain)
    return account
