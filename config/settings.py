import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE = os.getenv("MIKA_SERVICE", "panel")
if SERVICE not in {"panel", "shop"}:
    raise ValueError("MIKA_SERVICE must be panel or shop")
DEBUG = os.getenv("MIKA_DEBUG", "0") == "1"
SECRET_KEY = os.getenv("MIKA_SECRET_KEY", "")
if not SECRET_KEY:
    raise ValueError("Set MIKA_SECRET_KEY; run python tools/configure.py for local setup")
ALLOWED_HOSTS = os.getenv("MIKA_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
CSRF_TRUSTED_ORIGINS = [s for s in os.getenv("MIKA_CSRF_ORIGINS", "").split(",") if s]
ROOT_URLCONF = "config.panel_urls" if SERVICE == "panel" else "config.shop_urls"
WSGI_APPLICATION = "config.wsgi.application"
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "common", "hosting", "storefront",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "common.middleware.ServiceBoundaryMiddleware",
]
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"],
              "APP_DIRS": True, "OPTIONS": {"context_processors": [
                  "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
                  "django.contrib.messages.context_processors.messages", "common.context.brand",
              ]}}]
DATA_DIR = Path(os.getenv("MIKA_DATA_DIR", str(BASE_DIR / "var")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / f"{SERVICE}.sqlite3",
                          "OPTIONS": {"timeout": 30}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = DATA_DIR / "static"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"
SESSION_COOKIE_NAME = f"mika_{SERVICE}_session"
CSRF_COOKIE_NAME = f"mika_{SERVICE}_csrf"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
# Only bind Gunicorn to loopback behind the installer-managed Nginx proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
MIKA_API_TOKEN = os.getenv("MIKA_API_TOKEN", "")
MIKA_PANEL_URL = os.getenv("MIKA_PANEL_URL", "http://127.0.0.1:8001").rstrip("/")
MIKA_HOSTING_ROOT = Path(os.getenv("MIKA_HOSTING_ROOT", str(DATA_DIR / "sites")))
MIKA_PROVISION_MODE = os.getenv("MIKA_PROVISION_MODE", "demo")
MIKA_PHP_SOCKET = os.getenv("MIKA_PHP_SOCKET", "/run/php/php8.3-fpm.sock")
MIKA_SERVER_IP = os.getenv("MIKA_SERVER_IP", "127.0.0.1")
MIKA_CERTBOT_EMAIL = os.getenv("MIKA_CERTBOT_EMAIL", "")
MIKA_NAMESERVERS = os.getenv("MIKA_NAMESERVERS", "").split(",")
TRIPAY_MODE = os.getenv("TRIPAY_MODE", "sandbox")
TRIPAY_API_KEY = os.getenv("TRIPAY_API_KEY", "")
TRIPAY_PRIVATE_KEY = os.getenv("TRIPAY_PRIVATE_KEY", "")
TRIPAY_MERCHANT_CODE = os.getenv("TRIPAY_MERCHANT_CODE", "")
MYCHA_PUBLIC_URL = os.getenv("MYCHA_PUBLIC_URL", "http://127.0.0.1:8002").rstrip("/")
PAYMENT_CHANNELS = os.getenv("TRIPAY_CHANNELS", "BRIVA,BNIVA,QRIS").split(",")
EMAIL_BACKEND = os.getenv("MIKA_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("MIKA_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("MIKA_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("MIKA_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("MIKA_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.getenv("MIKA_FROM_EMAIL", "noreply@localhost")
