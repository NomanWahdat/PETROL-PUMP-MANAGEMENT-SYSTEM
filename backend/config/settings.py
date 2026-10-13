import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"true", "1", "yes"}


def env_list(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


DEBUG = env_bool("DJANGO_DEBUG")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY in the root .env or environment.")
if not DEBUG and (len(SECRET_KEY) < 50 or SECRET_KEY.startswith("local-development")):
    raise ImproperlyConfigured("Production requires a random DJANGO_SECRET_KEY of at least 50 characters.")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "apps.common", "apps.accounts", "apps.tenants", "apps.stations", "apps.audit",
    "apps.employees", "apps.fuel", "apps.operations", "apps.shifts", "apps.sales",
    "apps.suppliers", "apps.purchases", "apps.inventory", "apps.customers", "apps.cash",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

database_url = os.getenv("DATABASE_URL", "")
if database_url:
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise ImproperlyConfigured("DATABASE_URL must point to PostgreSQL. Use USE_SQLITE for local development.")
    DATABASES = {"default": dj_database_url.parse(database_url, conn_max_age=60, conn_health_checks=True)}
elif DEBUG and env_bool("USE_SQLITE"):
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    raise ImproperlyConfigured("Set DATABASE_URL, or enable DEBUG and USE_SQLITE for local development.")

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "fa"
LANGUAGES = [("fa", "Dari"), ("ps", "Pashto"), ("en", "English")]
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Kabul")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.getenv("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
MEDIA_URL = "/media/"
LOGO_STORAGE = os.getenv("DJANGO_LOGO_STORAGE", "file")
if LOGO_STORAGE not in {"file", "database"}:
    raise ImproperlyConfigured("DJANGO_LOGO_STORAGE must be file or database.")
# Transaction poolers cannot retain Django's named cursor across transactions.
if database_url:
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = env_bool("DJANGO_DISABLE_SERVER_SIDE_CURSORS", True)
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = 60 * 60 * 12
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_FAILURE_VIEW = "apps.common.errors.csrf_failure"
SECURE_SSL_REDIRECT = not DEBUG and env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if env_bool("DJANGO_TRUST_PROXY_SSL"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Share login throttling across production workers using Django's built-in cache.
cache_backend = os.getenv("DJANGO_CACHE_BACKEND", "database" if not DEBUG else "locmem")
if cache_backend not in {"database", "locmem"}:
    raise ImproperlyConfigured("DJANGO_CACHE_BACKEND must be database or locmem.")
if not DEBUG and cache_backend == "locmem":
    raise ImproperlyConfigured("Production login throttling requires a shared database cache.")
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.db.DatabaseCache" if cache_backend == "database" else "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": os.getenv("DJANGO_CACHE_LOCATION", "petrol_cache" if cache_backend == "database" else "petrol-development"),
}}
# Forwarded IPs are trusted only when an operator configures the proxy count.
try:
    proxy_count = int(os.getenv("DJANGO_NUM_PROXIES", "0"))
except ValueError as exc:
    raise ImproperlyConfigured("DJANGO_NUM_PROXIES must be a nonnegative integer.") from exc
if proxy_count < 0:
    raise ImproperlyConfigured("DJANGO_NUM_PROXIES must be a nonnegative integer.")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.SecureSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.ConfigPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.common.errors.exception_handler",
    "DEFAULT_THROTTLE_RATES": {"login": "10/min"},
    "NUM_PROXIES": proxy_count,
}
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
