"""Test settings: SQLite, no external services."""
from .settings import *  # noqa: F403

DEBUG = True
SECRET_KEY = 'test-secret-key-not-for-production'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
BASE_URL = 'http://testserver'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Avoid importing optional local overrides during tests
MEDIA_ROOT = BASE_DIR / 'test_media'  # noqa: F405
STATIC_ROOT = BASE_DIR / 'staticfiles'  # noqa: F405

# Tests must not call external AI APIs
AI_PROVIDER = 'off'
AI_API_KEY = ''
AI_MODEL = ''

# WhiteNoise optional in local venv — strip for tests
MIDDLEWARE = [m for m in MIDDLEWARE if 'whitenoise' not in m]  # noqa: F405
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
