import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from hosting.models import Account, Plan
from storefront.models import Order, Product


@pytest.fixture
def user(db):
    return User.objects.create_user("alice", "alice@example.test", "Long-test-password-2048!")


@pytest.fixture
def other(db):
    return User.objects.create_user("bob", "bob@example.test", "Different-password-2048!")


@pytest.fixture
def plan(db):
    return Plan.objects.create(slug="launch", name="Launch", disk_mb=1024, memory_mb=128, php_workers=2)


@pytest.fixture
def product(db):
    return Product.objects.create(slug="launch", name="Launch", tagline="Test", price=19000, disk_mb=1024, panel_plan="launch")


@pytest.fixture
def account(user, plan):
    return Account.objects.create(owner=user, plan=plan, external_id="MH-test", domain="alice.example.test",
                                  kind="static", expires_at=timezone.now() + timedelta(days=30))


@pytest.fixture
def order(user, product):
    return Order.objects.create(user=user, product=product, product_name="Launch", panel_plan="launch",
        domain="alice.example.test", kind="php", cycle=1, amount=19000, status="pending",
        payment_reference="T-123", payment_total=20000, payment_fee=1000)


@pytest.fixture
def shop(settings):
    settings.ROOT_URLCONF = "config.shop_urls"
    settings.SERVICE = "shop"
    settings.DEBUG = True
    settings.SECURE_SSL_REDIRECT = False
    settings.TRIPAY_PRIVATE_KEY = "fixture-signing-key-only"
    settings.TRIPAY_API_KEY = "fixture-api-only"
    settings.TRIPAY_MERCHANT_CODE = "TTEST"
    settings.MIKA_API_TOKEN = "fixture-panel-only"
    return settings


@pytest.fixture
def panel(settings, tmp_path):
    settings.ROOT_URLCONF = "config.panel_urls"
    settings.SERVICE = "panel"
    settings.DEBUG = True
    settings.SECURE_SSL_REDIRECT = False
    settings.MIKA_API_TOKEN = "fixture-panel-only"
    settings.MIKA_HOSTING_ROOT = tmp_path / "sites"
    settings.MIKA_PROVISION_MODE = "demo"
    settings.DATA_DIR = tmp_path
    settings.MYCHA_PUBLIC_URL = "https://shop.example.test"
    return settings
