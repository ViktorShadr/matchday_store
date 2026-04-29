import os
import sys
from pathlib import Path

from csp.constants import NONE, NONCE, SELF
from dotenv import load_dotenv

from config.logging_utils import build_logging_config
from config.sentry import init_sentry

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set")


def env_bool(name: str, default: bool = False) -> bool:
    """Преобразует значение переменной окружения в bool."""
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str) -> list[str]:
    """Преобразует comma-separated переменную окружения в список."""
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()]

if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "csp",
    "djcelery_email",
    "orders.apps.OrdersConfig",
    "payments.apps.PaymentsConfig",
    "store.apps.StoreConfig",
    "users.apps.UsersConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.RequestIdMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.navigation_permissions",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "ru-RU"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

if "test" in sys.argv:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

AUTH_USER_MODEL = "users.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/users/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "noreply@matchday-store.com",
)
STAFF_ORDER_NOTIFICATION_EMAILS = env_list("STAFF_ORDER_NOTIFICATION_EMAILS")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
EMAIL_CONFIRMATION_TOKEN_TTL_HOURS = int(os.getenv("EMAIL_CONFIRMATION_TOKEN_TTL_HOURS", "24"))

STORE_PICKUP_LOCATION_CODE = os.getenv("STORE_PICKUP_LOCATION_CODE", "main-store")
STORE_PICKUP_LOCATION_NAME = os.getenv(
    "STORE_PICKUP_LOCATION_NAME",
    "Магазин ФК «Шинник»",
)
STORE_PICKUP_ADDRESS = os.getenv(
    "STORE_PICKUP_ADDRESS",
    "г. Ярославль, пл. Труда, 3",
)
STORE_PICKUP_HOURS = os.getenv(
    "STORE_PICKUP_HOURS",
    "пн-пт с 10:00 до 16:00\nсб-вс выходной",
)
STORE_PICKUP_PHONE = os.getenv(
    "STORE_PICKUP_PHONE",
    "+7 (4852) 00-00-00",
)

CACHE_URL = (os.getenv("CACHE_URL") or "").strip()
if CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CACHE_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "matchday-store-default",
        }
    }

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "same-origin")
SECURE_CROSS_ORIGIN_OPENER_POLICY = os.getenv("SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin")
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]

RATELIMIT_ENABLE = env_bool("RATELIMIT_ENABLE", True)
RATELIMIT_USE_CACHE = os.getenv("RATELIMIT_USE_CACHE", "default")
RATELIMIT_IP_META_KEY = os.getenv("RATELIMIT_IP_META_KEY") or None
RATELIMIT_LOGIN_IP_RATE = os.getenv("RATELIMIT_LOGIN_IP_RATE", "20/10m")
RATELIMIT_LOGIN_CREDENTIAL_RATE = os.getenv("RATELIMIT_LOGIN_CREDENTIAL_RATE", "10/10m")
RATELIMIT_REGISTRATION_IP_RATE = os.getenv("RATELIMIT_REGISTRATION_IP_RATE", "12/1h")
RATELIMIT_REGISTRATION_EMAIL_RATE = os.getenv("RATELIMIT_REGISTRATION_EMAIL_RATE", "5/1h")
RATELIMIT_CONFIRM_RESEND_IP_RATE = os.getenv("RATELIMIT_CONFIRM_RESEND_IP_RATE", "8/1h")
RATELIMIT_CONFIRM_RESEND_USER_RATE = os.getenv("RATELIMIT_CONFIRM_RESEND_USER_RATE", "5/1h")
RATELIMIT_CHECKOUT_IP_RATE = os.getenv("RATELIMIT_CHECKOUT_IP_RATE", "20/10m")
RATELIMIT_CHECKOUT_USER_RATE = os.getenv("RATELIMIT_CHECKOUT_USER_RATE", "10/10m")

_CSP_DIRECTIVES = {
    "default-src": [SELF],
    "base-uri": [SELF],
    "form-action": [SELF],
    "frame-ancestors": [SELF],
    "img-src": [SELF, "data:"],
    "font-src": [SELF, "data:"],
    "script-src": [SELF, NONCE],
    "style-src": [SELF, "'unsafe-inline'"],
    "connect-src": [SELF],
    "object-src": [NONE],
}

_CSP_POLICY = {"DIRECTIVES": _CSP_DIRECTIVES}
if env_bool("CSP_ENFORCE", not DEBUG):
    CONTENT_SECURITY_POLICY = _CSP_POLICY
else:
    CONTENT_SECURITY_POLICY_REPORT_ONLY = _CSP_POLICY

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_JSON = env_bool("LOG_JSON", not DEBUG)
LOGGING = build_logging_config(debug=DEBUG, log_level=LOG_LEVEL, json_logs=LOG_JSON)

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)

    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        True,
    )
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", True)

init_sentry(debug=DEBUG)
