import os
import sys
from pathlib import Path

from celery.schedules import crontab
from csp.constants import NONCE, NONE, SELF
from dotenv import load_dotenv
from kombu import Queue

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

METRIKA_ENABLED = env_bool("METRIKA_ENABLED", False)
METRIKA_COUNTER_ID = os.getenv("METRIKA_COUNTER_ID", "").strip()
if METRIKA_COUNTER_ID and not METRIKA_COUNTER_ID.isdigit():
    raise ValueError("METRIKA_COUNTER_ID must contain only digits")
METRIKA_REQUIRE_CONSENT = env_bool("METRIKA_REQUIRE_CONSENT", False)
METRIKA_ACTIVE = not DEBUG and METRIKA_ENABLED and bool(METRIKA_COUNTER_ID)

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
    "analytics.apps.AnalyticsConfig",
    "csp",
    "orders.apps.OrdersConfig",
    "payments.apps.PaymentsConfig",
    "store.apps.StoreConfig",
    "support.apps.SupportConfig",
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
]

if not METRIKA_ACTIVE:
    MIDDLEWARE.append("django.middleware.clickjacking.XFrameOptionsMiddleware")

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
                "analytics.context_processors.yandex_metrika",
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

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES = (
    Queue("default"),
    Queue("email"),
)
CELERY_TASK_ROUTES = {
    "orders.tasks.send_order_notification": {"queue": "email"},
    "orders.tasks.send_staff_new_order_notification": {"queue": "email"},
    "support.tasks.send_support_request_notification": {"queue": "email"},
    "users.tasks.send_confirmation_email": {"queue": "email"},
    "users.tasks.send_welcome_email": {"queue": "email"},
}
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "1"))

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or EMAIL_HOST_USER or "noreply@shinnik-store.example"
STAFF_ORDER_NOTIFICATION_EMAILS = env_list("STAFF_ORDER_NOTIFICATION_EMAILS")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
EMAIL_CONFIRMATION_TOKEN_TTL_HOURS = int(os.getenv("EMAIL_CONFIRMATION_TOKEN_TTL_HOURS", "24"))
GUEST_ORDER_TOKEN_TTL_DAYS = int(os.getenv("GUEST_ORDER_TOKEN_TTL_DAYS", "30"))

STORE_BRAND_NAME = os.getenv("STORE_BRAND_NAME", "ФК «Шинник»")
STORE_SUPPORT_EMAIL = os.getenv("STORE_SUPPORT_EMAIL") or DEFAULT_FROM_EMAIL
SUPPORT_NOTIFICATION_EMAILS = env_list("SUPPORT_NOTIFICATION_EMAILS")
STORE_PICKUP_LOCATION_CODE = os.getenv("STORE_PICKUP_LOCATION_CODE", "main-store")
STORE_PICKUP_LOCATION_NAME = os.getenv(
    "STORE_PICKUP_LOCATION_NAME",
    "Фирменный магазин ФК «Шинник»",
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
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
CSRF_FAILURE_VIEW = "users.views.csrf_failure"

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "same-origin")
SECURE_CROSS_ORIGIN_OPENER_POLICY = os.getenv("SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin")
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", False)
if env_bool("USE_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)

RATELIMIT_ENABLE = env_bool("RATELIMIT_ENABLE", True)
RATELIMIT_USE_CACHE = os.getenv("RATELIMIT_USE_CACHE", "default")
RATELIMIT_IP_META_KEY = os.getenv("RATELIMIT_IP_META_KEY") or None
RATELIMIT_LOGIN_IP_RATE = os.getenv("RATELIMIT_LOGIN_IP_RATE", "20/10m")
RATELIMIT_LOGIN_CREDENTIAL_RATE = os.getenv("RATELIMIT_LOGIN_CREDENTIAL_RATE", "10/10m")
RATELIMIT_REGISTRATION_IP_RATE = os.getenv("RATELIMIT_REGISTRATION_IP_RATE", "12/1h")
RATELIMIT_REGISTRATION_EMAIL_RATE = os.getenv("RATELIMIT_REGISTRATION_EMAIL_RATE", "5/1h")
RATELIMIT_CONFIRM_RESEND_IP_RATE = os.getenv("RATELIMIT_CONFIRM_RESEND_IP_RATE", "8/1h")
RATELIMIT_CONFIRM_RESEND_USER_RATE = os.getenv("RATELIMIT_CONFIRM_RESEND_USER_RATE", "5/1h")
RATELIMIT_PASSWORD_RESET_IP_RATE = os.getenv("RATELIMIT_PASSWORD_RESET_IP_RATE", "5/1h")
RATELIMIT_PASSWORD_RESET_EMAIL_RATE = os.getenv("RATELIMIT_PASSWORD_RESET_EMAIL_RATE", "5/1h")
RATELIMIT_CHECKOUT_IP_RATE = os.getenv("RATELIMIT_CHECKOUT_IP_RATE", "12/10m")
RATELIMIT_CHECKOUT_USER_RATE = os.getenv("RATELIMIT_CHECKOUT_USER_RATE", "5/10m")
RATELIMIT_SUPPORT_POST_RATE = os.getenv("RATELIMIT_SUPPORT_POST_RATE", "5/10m")
CHECKOUT_MAX_ACTIVE_ORDERS = int(os.getenv("CHECKOUT_MAX_ACTIVE_ORDERS", "3"))
# Guest active-order limits protect stock reservations from repeated unpaid guest checkouts.
CHECKOUT_MAX_ACTIVE_GUEST_ORDERS_BY_EMAIL = int(os.getenv("CHECKOUT_MAX_ACTIVE_GUEST_ORDERS_BY_EMAIL", "3"))
CHECKOUT_MAX_ACTIVE_GUEST_ORDERS_BY_PHONE = int(os.getenv("CHECKOUT_MAX_ACTIVE_GUEST_ORDERS_BY_PHONE", "3"))
CHECKOUT_MAX_ACTIVE_GUEST_ORDERS_BY_SESSION = int(os.getenv("CHECKOUT_MAX_ACTIVE_GUEST_ORDERS_BY_SESSION", "3"))
CHECKOUT_MAX_ACTIVE_GUEST_ORDERS_BY_IP = int(os.getenv("CHECKOUT_MAX_ACTIVE_GUEST_ORDERS_BY_IP", "10"))
CHECKOUT_MAX_QTY_PER_SKU = int(os.getenv("CHECKOUT_MAX_QTY_PER_SKU", "5"))
STOCK_RESERVE_MODE_ENABLED = env_bool("STOCK_RESERVE_MODE_ENABLED", True)
ORDER_PICKUP_RETENTION_BUSINESS_DAYS = int(os.getenv("ORDER_PICKUP_RETENTION_BUSINESS_DAYS", "3"))
ORDER_AUTO_CANCEL_BATCH_SIZE = int(os.getenv("ORDER_AUTO_CANCEL_BATCH_SIZE", "100"))
ORDER_AUTO_CANCEL_INTERVAL_SECONDS = int(os.getenv("ORDER_AUTO_CANCEL_INTERVAL_SECONDS", "900"))
default_thumbnail_generation_mode = "sync" if DEBUG else "async"
PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE = (
    os.getenv("PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE", default_thumbnail_generation_mode).strip().lower()
)
if PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE not in {"sync", "async"}:
    raise ValueError("PRODUCT_IMAGE_THUMBNAIL_GENERATION_MODE must be 'sync' or 'async'")

CELERY_BEAT_SCHEDULE = {
    "auto-cancel-expired-pickup-orders": {
        "task": "orders.tasks.auto_cancel_expired_pickup_orders",
        "schedule": ORDER_AUTO_CANCEL_INTERVAL_SECONDS,
    },
    "recover-stale-outbox-notifications": {
        "task": "orders.tasks.recover_stale_outbox_notifications",
        "schedule": crontab(minute="*/10"),
    },
}

_CSP_DIRECTIVES = {
    "default-src": [SELF],
    "base-uri": [SELF],
    "form-action": [SELF],
    "frame-ancestors": [SELF],
    "img-src": [SELF, "data:", "blob:"],
    "font-src": [SELF, "data:"],
    "script-src": [SELF, NONCE, "https://cdn.jsdelivr.net"],
    "style-src": [SELF, "'unsafe-inline'", "https://cdn.jsdelivr.net"],
    "connect-src": [SELF],
    "object-src": [NONE],
}

YANDEX_METRIKA_HTTPS_SOURCES = [
    "https://mc.yandex.ru",
    "https://mc.yandex.az",
    "https://mc.yandex.by",
    "https://mc.yandex.co.il",
    "https://mc.yandex.com",
    "https://mc.yandex.com.am",
    "https://mc.yandex.com.ge",
    "https://mc.yandex.com.tr",
    "https://mc.yandex.ee",
    "https://mc.yandex.fr",
    "https://mc.yandex.kg",
    "https://mc.yandex.kz",
    "https://mc.yandex.lt",
    "https://mc.yandex.lv",
    "https://mc.yandex.md",
    "https://mc.yandex.tj",
    "https://mc.yandex.tm",
    "https://mc.yandex.uz",
    "https://mc.webvisor.com",
    "https://mc.webvisor.org",
]
YANDEX_METRIKA_WSS_SOURCES = [
    "wss://mc.yandex.ru",
    "wss://mc.yandex.az",
    "wss://mc.yandex.by",
    "wss://mc.yandex.co.il",
    "wss://mc.yandex.com",
    "wss://mc.yandex.com.am",
    "wss://mc.yandex.com.ge",
    "wss://mc.yandex.com.tr",
    "wss://mc.yandex.ee",
    "wss://mc.yandex.fr",
    "wss://mc.yandex.kg",
    "wss://mc.yandex.kz",
    "wss://mc.yandex.lt",
    "wss://mc.yandex.lv",
    "wss://mc.yandex.md",
    "wss://mc.yandex.tj",
    "wss://mc.yandex.tm",
    "wss://mc.yandex.uz",
    "wss://mc.webvisor.com",
    "wss://mc.webvisor.org",
]

if METRIKA_ACTIVE:
    _CSP_DIRECTIVES["script-src"] += ["https://mc.yandex.ru", "https://yastatic.net"]
    _CSP_DIRECTIVES["img-src"] += YANDEX_METRIKA_HTTPS_SOURCES
    _CSP_DIRECTIVES["connect-src"] += YANDEX_METRIKA_HTTPS_SOURCES + YANDEX_METRIKA_WSS_SOURCES
    _CSP_DIRECTIVES["child-src"] = [SELF, "blob:"] + YANDEX_METRIKA_HTTPS_SOURCES
    _CSP_DIRECTIVES["frame-src"] = [SELF, "blob:"] + YANDEX_METRIKA_HTTPS_SOURCES
    _CSP_DIRECTIVES["frame-ancestors"] = [SELF, "blob:"] + YANDEX_METRIKA_HTTPS_SOURCES

_CSP_POLICY = {"DIRECTIVES": _CSP_DIRECTIVES}
if env_bool("CSP_ENFORCE", not DEBUG):
    CONTENT_SECURITY_POLICY = _CSP_POLICY
else:
    CONTENT_SECURITY_POLICY_REPORT_ONLY = _CSP_POLICY

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_JSON = env_bool("LOG_JSON", not DEBUG)
LOGGING = build_logging_config(debug=DEBUG, log_level=LOG_LEVEL, json_logs=LOG_JSON)

init_sentry(debug=DEBUG)
