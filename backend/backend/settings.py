"""Minimal Django configuration for the repository evaluation API."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# A secret is required in production; allow a fixed, non-secret value for local development.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if DEBUG and not SECRET_KEY:
    SECRET_KEY = "django-insecure-local-development-only"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
if render_hostname := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(render_hostname)

INSTALLED_APPS = []

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "backend.urls"
WSGI_APPLICATION = "backend.wsgi.application"

# No database, admin, auth, templates, or Django static files are required.
DATABASES = {}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Per-process only: entries are lost on restart and are not shared by workers.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "repository-evaluations",
    }
}
