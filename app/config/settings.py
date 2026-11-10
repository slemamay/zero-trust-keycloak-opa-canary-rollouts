"""
Django settings for config project (Projet 44 - Membre 2).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-d!z-hc4qtuh%vu0wewo#@u2(bf%$1y20bwi=97of@uk&g2t78*",
)

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "app"]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'mozilla_django_oidc',
    'banking',
    'authn',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # M4 ajoutera ici : 'authz.middleware.PolicyEnforcementMiddleware'
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database (PostgreSQL du docker-compose)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "projet44"),
        "USER": os.getenv("DB_USER", "projet44"),
        "PASSWORD": os.getenv("DB_PASSWORD", "projet44pass"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# --- Keycloak / OIDC (Membre 2) ---

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "mozilla_django_oidc.auth.OIDCAuthenticationBackend",
]

_KC_PUBLIC = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
_KC_INTERNAL = os.getenv("KEYCLOAK_INTERNAL_URL", _KC_PUBLIC)
_REALM = os.getenv("KEYCLOAK_REALM", "projet44")
_PUB = f"{_KC_PUBLIC}/realms/{_REALM}/protocol/openid-connect"
_INT = f"{_KC_INTERNAL}/realms/{_REALM}/protocol/openid-connect"

OIDC_RP_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "django-app")
OIDC_RP_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET")
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_RP_SCOPES = "openid email profile"
OIDC_USE_PKCE = True

OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_PUB}/auth"    # navigateur -> adresse publique
OIDC_OP_TOKEN_ENDPOINT = f"{_INT}/token"           # serveur -> adresse interne
OIDC_OP_USER_ENDPOINT = f"{_INT}/userinfo"
OIDC_OP_JWKS_ENDPOINT = f"{_INT}/certs"

OIDC_STORE_ACCESS_TOKEN = True
LOGIN_REDIRECT_URL = "http://localhost:8000/"
LOGOUT_REDIRECT_URL = "http://localhost:8000/"