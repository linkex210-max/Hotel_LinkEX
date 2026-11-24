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
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('SECRET_KEY must be configured when DEBUG is disabled')
    SECRET_KEY = 'django-insecure-local-development-only-key'
ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]

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
    DATABASES = {
        'default': {
            'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.postgresql'),
            'NAME': os.getenv('DB_NAME', 'hotel_db'),
            'USER': os.getenv('DB_USER', 'hotel_user'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'hotel_pass123'),
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

# CORS Settings
CORS_ALLOW_ALL_ORIGINS = DEBUG
SECURE_SSL_REDIRECT = not DEBUG and os.getenv('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 't')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
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
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
JWT_ACCESS_TOKEN_LIFETIME_MINUTES = int(os.getenv('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 60))
JWT_REFRESH_TOKEN_LIFETIME_DAYS = int(os.getenv('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 7))
