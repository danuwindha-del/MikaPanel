import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Account, LoginToken, Plan, ProvisionJob
from .validation import domain_name


def api_auth(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        supplied = request.headers.get("Authorization", "")
        token = settings.MIKA_API_TOKEN
        if not token or not hmac.compare_digest(supplied, "Bearer " + token):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        return view(request, *args, **kwargs)
    return csrf_exempt(inner)


def serialize(account):
    return {"id": str(account.id), "external_id": account.external_id, "domain": account.domain,
            "status": account.status, "kind": account.kind, "plan": account.plan.slug,
            "expires_at": account.expires_at.isoformat(), "server_ip": settings.MIKA_SERVER_IP,
            "mode": settings.MIKA_PROVISION_MODE}


@api_auth
@require_POST
def provision(request):
    try:
        body = json.loads(request.body)
        external_id = str(body["external_id"])
        if not external_id or len(external_id) > 100:
            raise ValueError("Invalid external_id")
        domain = domain_name(body["domain"])
        email = str(body["email"]).strip().lower()
        from django.core.validators import validate_email
        validate_email(email)
        kind = body["kind"]
        if kind not in {"static", "php"}:
            raise ValueError("Unsupported hosting type")
        plan = Plan.objects.get(slug=body["plan"], active=True)
        days = int(body.get("days", 30))
        if not 1 <= days <= 366:
            raise ValueError("Invalid duration")
        existing = Account.objects.filter(external_id=external_id).first()
        if existing:
            if (existing.domain, existing.owner.email, existing.kind, existing.plan.slug) != (domain, email, kind, plan.slug):
                return JsonResponse({"error": "Idempotency conflict"}, status=409)
            return JsonResponse(serialize(existing))
        with transaction.atomic():
            # Stable external identity, independent from mutable email and local login usernames.
            customer_id = str(body["customer_id"])
            if not customer_id or len(customer_id) > 100:
                raise ValueError("Invalid customer_id")
            username = "mycha_" + hashlib.sha256(customer_id.encode()).hexdigest()[:32]
            owner, created = User.objects.get_or_create(username=username, defaults={"email": email})
            if created:
                owner.set_unusable_password()
                owner.save(update_fields=["password"])
            elif owner.email != email:
                raise ValueError("Customer identity mismatch")
            account = Account.objects.create(external_id=external_id, domain=domain, owner=owner, plan=plan,
                                             kind=kind, expires_at=timezone.now() + timedelta(days=days))
            ProvisionJob.objects.create(account=account, action="create")
        return JsonResponse(serialize(account), status=201)
    except (KeyError, ValueError, TypeError, ValidationError, Plan.DoesNotExist, UnicodeError):
        return JsonResponse({"error": "Invalid request or unavailable plan"}, status=400)
    except IntegrityError:
        return JsonResponse({"error": "Domain or identity already registered; retry idempotently"}, status=409)


@api_auth
def account_status(request, external_id):
    account = Account.objects.filter(external_id=external_id).first()
    if not account:
        return JsonResponse({"error": "Not found"}, status=404)
    return JsonResponse(serialize(account))


@api_auth
@require_POST
def sso_token(request, external_id):
    account = Account.objects.filter(external_id=external_id, status="active").first()
    if not account:
        return JsonResponse({"error": "Active account not found"}, status=404)
    token = secrets.token_urlsafe(32)
    LoginToken.objects.create(digest=hashlib.sha256(token.encode()).hexdigest(), owner=account.owner,
                              expires_at=timezone.now() + timedelta(seconds=60))
    return JsonResponse({"token": token, "expires_in": 60})
