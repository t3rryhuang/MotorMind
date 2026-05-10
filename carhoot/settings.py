"""
Django settings for Car-Hoot (carhoot project).
"""

import os
from pathlib import Path

from django.contrib.messages import constants as message_constants
from dotenv import load_dotenv

load_dotenv()

MESSAGE_TAGS = {message_constants.ERROR: "danger"}

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-only-change-in-production")

DEBUG = os.environ.get("DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1,testserver",
    ).split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "courses",
    "quizzes",
    "ar_tasks",
    "resources",
    "study_content",
    "tutor",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "carhoot.urls"

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
                "accounts.context_processors.user_profile",
            ],
        },
    },
]

WSGI_APPLICATION = "carhoot.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Leading slash so URLs are always from site root (avoids wrong paths on nested routes).
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Collected copies for production (`collectstatic`); not used by `runserver` for dev serving.
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Large resource uploads (e.g. full PDF textbooks). Django defaults (~2.5 MB) block big multipart bodies.
DATA_UPLOAD_MAX_MEMORY_NUMBER = int(
    os.environ.get("DATA_UPLOAD_MAX_MEMORY_MB", "200")
) * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024  # buffer in RAM before spilling to temp file during parse

# Chroma persistent store (vectors + chunk documents). Not SQLite.
VECTOR_DB_PATH = BASE_DIR / "vector_db"
CHROMA_COLLECTION_NAME = "carhoot_resources"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Google Gemini (also read via os.environ in several services) ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_MODEL_NAME = os.environ.get("GOOGLE_MODEL_NAME", "gemma-3-27b-it")

# --- ElevenLabs (text-to-speech for AI tutor only) ---
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
