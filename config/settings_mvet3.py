"""Isolated PR 0 laboratory. Never configure production with this module."""
from .settings import *  # noqa: F403

# Fixed identities: inherited production POSTGRES_* values cannot redirect Django.
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "mvet3_lab", "USER": "mvet3_lab", "HOST": "lab-db",
    "PORT": "5432", "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
    "CONN_MAX_AGE": 60,
}}
BLING_NETWORK_ENABLED = False
BLING_CLIENT_ID = BLING_CLIENT_SECRET = BLING_REDIRECT_URI = ""
BLING_ISSUER_CNPJ = BLING_TOKEN_KEY = ""
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "lab-web", "testserver"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:8001", "http://127.0.0.1:8001"]
SESSION_COOKIE_NAME = "mvet3_sessionid"
CSRF_COOKIE_NAME = "mvet3_csrftoken"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT = False
DEBUG = False

COMPANY_CONTEXT_ENABLED = True
