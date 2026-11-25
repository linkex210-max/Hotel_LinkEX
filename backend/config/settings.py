import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / '.env')

# Add apps folder to Python path
sys.path.insert(0, str(BASE_DIR / 'apps'))

# Quick-start development settings - unsuitable for production
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

INSECURE_SECRET_KEYS = {
    'django-insecure-local-development-only-key',
    'django-insecure-hotel-linkex-dev-secret-key-change-in-production-2026',
    'hotel-linkex-jwt-secret-key-2026',
    'changeme',
    'secret',
}

def _validate_production_secret(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f'{name} must be configured when DEBUG is disabled')
    if value.startswith('django-insecure-') or value in INSECURE_SECRET_KEYS or len(value) < 32:
        raise RuntimeError(f'{name} is insecure or too short for production (minimum 32 chars, no default/insecure prefix)')
    return value

SECRET_KEY = os.getenv('SECRET_KEY')
if not DEBUG:
    SECRET_KEY = _validate_production_secret(SECRET_KEY, 'SECRET_KEY')
elif not SECRET_KEY:
    SECRET_KEY = 'django-insecure-local-development-only-key'

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]
if not DEBUG:
    if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
        raise RuntimeError('ALLOWED_HOSTS must not be empty or contain wildcard "*" when DEBUG is disabled')

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'corsheaders',
]

LOCAL_APPS = [
    'apps.users',
    'apps.properties',
    'apps.bookings',
    'apps.finance',
    'apps.notifications',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
USE_SQLITE = os.getenv('USE_SQLITE', 'False').lower() in ('true', '1', 't')

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 20,
            },
        }
    }
else:
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    if not DEBUG and (not DB_PASSWORD or DB_PASSWORD == 'hotel_pass123'):
        raise RuntimeError('DB_PASSWORD must be configured with a strong non-default password when DEBUG is disabled')
    DATABASES = {
        'default': {
            'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.postgresql'),
            'NAME': os.getenv('DB_NAME', 'hotel_db'),
            'USER': os.getenv('DB_USER', 'hotel_user'),
            'PASSWORD': DB_PASSWORD or 'hotel_pass123',
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Custom User Model
# Once models.py is defined in users:
AUTH_USER_MODEL = 'users.User'

# Internationalization
LANGUAGE_CODE = 'ar-sa'
TIME_ZONE = 'Asia/Riyadh'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS & Security Settings
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if origin.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()
]

SECURE_SSL_REDIRECT = not DEBUG and os.getenv('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 't')
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = os.getenv('USE_X_FORWARDED_HOST', 'True').lower() in ('true', '1', 't')
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'cancel-expired-pending-bookings-every-minute': {
        'task': 'apps.notifications.tasks.cancel_expired_pending_bookings',
        'schedule': 60.0,
    },
}

# JWT Configuration
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
if not DEBUG:
    JWT_SECRET_KEY = _validate_production_secret(JWT_SECRET_KEY, 'JWT_SECRET_KEY')
elif not JWT_SECRET_KEY:
    JWT_SECRET_KEY = SECRET_KEY
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
JWT_ACCESS_TOKEN_LIFETIME_MINUTES = int(os.getenv('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 60))
JWT_REFRESH_TOKEN_LIFETIME_DAYS = int(os.getenv('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 7))
