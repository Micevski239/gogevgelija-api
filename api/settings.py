import os
from pathlib import Path
from datetime import timedelta
import dj_database_url
import logging.config
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

# -------------------- Security --------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or (
    "dev-only-do-not-use-in-prod" if os.getenv("DJANGO_DEBUG", "0") == "1"
    else (_ for _ in ()).throw(ValueError("DJANGO_SECRET_KEY enviroment variable must be set in production"))
)
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "https://admin.gogevgelija.com").split(",")

CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "1") == "1"
    SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "1") == "1"
    SECURE_REFERRER_POLICY = os.getenv("DJANGO_SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# -------------------- Apps --------------------
INSTALLED_APPS = [
    "django.contrib.admin","django.contrib.auth","django.contrib.contenttypes",
    "django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles",
    "rest_framework","corsheaders","modeltranslation","core.apps.CoreConfig",
]
USE_SPACES = os.getenv("USE_SPACES", "1") == "1"
if USE_SPACES:
    INSTALLED_APPS += ["storages"]

# -------------------- Middleware --------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
]
if not USE_SPACES:
    MIDDLEWARE += ["whitenoise.middleware.WhiteNoiseMiddleware"]
MIDDLEWARE += [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "api.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "api.wsgi.application"

# -------------------- Database --------------------
db_url = os.getenv("DATABASE_URL", "sqlite:///" + str(BASE_DIR / "db.sqlite3"))
ssl_require = not DEBUG and "sqlite" not in db_url.lower()
DATABASES = {"default": dj_database_url.parse(db_url, conn_max_age=600, ssl_require=ssl_require, conn_health_checks=True)}
if not DEBUG and "postgres" in db_url.lower():
    DATABASES["default"]["OPTIONS"] = {"sslmode": "require", "sslcert": None, "sslkey": None, "sslrootcert": None}

# -------------------- DRF / JWT --------------------
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": os.getenv("JWT_ROTATE_REFRESH_TOKENS", "1") == "1",
    "BLACKLIST_AFTER_ROTATION": os.getenv("JWT_BLACKLIST_AFTER_ROTATION", "1") == "1",
}

# -------------------- Static / Media --------------------
# Always define STATIC_ROOT so collectstatic pre-checks pass
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "core" / "static"]

if USE_SPACES:
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL")

    AWS_S3_CUSTOM_DOMAIN = os.getenv(
        "AWS_S3_CUSTOM_DOMAIN",
        f"{AWS_STORAGE_BUCKET_NAME}.{AWS_S3_REGION_NAME}.digitaloceanspaces.com",
    )
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=31536000, public"}
    AWS_QUERYSTRING_AUTH = False
    AWS_DEFAULT_ACL = "public-read"

    from storages.backends.s3boto3 import S3Boto3Storage

    class StaticRootS3Boto3Storage(S3Boto3Storage):
        location = "static"

    class MediaRootS3Boto3Storage(S3Boto3Storage):
        location = "media"

    STORAGES = {
        "staticfiles": {"BACKEND": "api.settings.StaticRootS3Boto3Storage"},
        "default": {"BACKEND": "api.settings.MediaRootS3Boto3Storage"},
    }

    STATIC_URL = os.getenv("STATIC_URL", f"https://{AWS_S3_CUSTOM_DOMAIN}/static/")
    MEDIA_URL = os.getenv("MEDIA_URL", f"https://{AWS_S3_CUSTOM_DOMAIN}/media/")
else:
    STORAGES = {
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    }
    STATIC_URL = "/static/"
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"

# -------------------- CORS --------------------
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "0") == "1"
if not CORS_ALLOW_ALL_ORIGINS:
    _cors = os.getenv("CORS_ALLOWED_ORIGINS", "")
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]

# -------------------- Proxy --------------------
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG and os.getenv("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"

# -------------------- i18n --------------------
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
LANGUAGES = [("en", "English"), ("mk", "Macedonian")]
MODELTRANSLATION_DEFAULT_LANGUAGE = "en"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Directory that holds shared translation resources
TRANSLATIONS_DIR = BASE_DIR.parent / "translations"

# -------------------- Admin toggle --------------------
ADMIN_ENABLED = os.getenv("DJANGO_ADMIN_ENABLED", "1" if DEBUG else "0") == "1"

# -------------------- Logging --------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}", "style": "{"},
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "file": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(BASE_DIR, "logs", "django_errors.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "console": {
            "level": "INFO" if DEBUG else "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "simple" if DEBUG else "verbose",
        },
        "security": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(BASE_DIR, "logs", "security.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["console", "file"] if not DEBUG else ["console"], "level": "INFO", "propagate": False},
        "django.security": {"handlers": ["console", "security"] if not DEBUG else ["console"], "level": "INFO", "propagate": False},
        "core": {"handlers": ["console", "file"] if not DEBUG else ["console"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

# -------------------- Health --------------------
HEALTH_CHECK_ENABLED = os.getenv("HEALTH_CHECK_ENABLED", "1") == "1"

# -------------------- Email --------------------
if not DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")
    _admin = os.getenv("ADMIN_EMAIL")
    ADMINS = [("Admin", _admin)] if _admin else []
    MANAGERS = ADMINS
    LOGGING["handlers"]["mail_admins"] = {"level": "ERROR", "class": "django.utils.log.AdminEmailHandler", "include_html": True}
    LOGGING["loggers"]["django"]["handlers"].append("mail_admins")

# -------------------- Cache --------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache" if os.getenv("REDIS_URL") else "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": os.getenv("REDIS_URL", "unique-snowflake"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"} if os.getenv("REDIS_URL") else {},
        "KEY_PREFIX": "gogevgelija",
        "TIMEOUT": 300,
    }
}

# -------------------- Sessions --------------------
SESSION_ENGINE = "django.contrib.sessions.backends.cache" if os.getenv("REDIS_URL") else "django.contrib.sessions.backends.db"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "1209600"))
