import os
import runpy
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings, Client

SETTINGS = Path(__file__).resolve().parent.parent / 'fishing_ai' / 'settings.py'
PROD = {'DJANGO_ENV':'production', 'DEBUG':'False', 'DJANGO_SECRET_KEY':'test-only-production-settings-key',
        'DATABASE_URL':'postgresql://test:test@localhost:5432/fishing', 'ALLOWED_HOSTS':'app.up.railway.app',
        'CSRF_TRUSTED_ORIGINS':'https://app.up.railway.app'}


class ProductionSettingsTests(SimpleTestCase):
    def load(self, environment):
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(SETTINGS))

    def test_local_sqlite_is_preserved(self):
        settings = self.load({})
        self.assertTrue(settings['DEBUG'])
        self.assertEqual(settings['DATABASES']['default']['ENGINE'], 'django.db.backends.sqlite3')

    def test_production_database_proxy_and_static_settings(self):
        settings = self.load(PROD)
        self.assertFalse(settings['DEBUG'])
        self.assertEqual(settings['DATABASES']['default']['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(settings['DATABASES']['default']['NAME'], 'fishing')
        self.assertEqual(settings['CSRF_TRUSTED_ORIGINS'], ['https://app.up.railway.app'])
        self.assertTrue(settings['SESSION_COOKIE_SECURE'])
        self.assertTrue(settings['CSRF_COOKIE_SECURE'])
        self.assertEqual(settings['SECURE_PROXY_SSL_HEADER'], ('HTTP_X_FORWARDED_PROTO','https'))
        self.assertEqual(settings['MIDDLEWARE'][1], 'whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertIn('CompressedManifest', settings['STORAGES']['staticfiles']['BACKEND'])

    def test_missing_production_secrets_database_and_hosts_fail_closed(self):
        for field in ('DJANGO_SECRET_KEY', 'DATABASE_URL', 'ALLOWED_HOSTS'):
            with self.subTest(field=field):
                env = {**PROD, field:''}
                with self.assertRaises(ImproperlyConfigured): self.load(env)
        for field, value in [('DEBUG','True'),('DATABASE_URL','sqlite:///db.sqlite3'),('ALLOWED_HOSTS','*')]:
            with self.assertRaises(ImproperlyConfigured): self.load({**PROD,field:value})

    def test_railway_detected_without_explicit_production_flag(self):
        env = {**PROD,'DJANGO_ENV':'','RAILWAY_ENVIRONMENT_ID':'test-environment'}
        self.assertTrue(self.load(env)['PRODUCTION'])
        with self.assertRaises(ImproperlyConfigured): self.load({**env,'DEBUG':'True'})

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['app.up.railway.app'], SECURE_SSL_REDIRECT=True,
                       SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https'))
    def test_https_proxy_does_not_redirect_loop(self):
        response = Client().get('/kirjaudu/', HTTP_HOST='app.up.railway.app', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code,200)
        self.assertEqual(Client().get('/kirjaudu/', HTTP_HOST='app.up.railway.app').status_code,301)


    def test_debug_false_values_in_production(self):
        for value in ('False', 'false', '0', 'no', 'off', 'FALSE', ' Off '):
            with self.subTest(value=value):
                self.assertIs(self.load({**PROD, 'DEBUG': value})['DEBUG'], False)

    def test_debug_true_values_in_development_and_rejected_in_production(self):
        for value in ('True', 'true', '1', 'yes', 'on', 'TRUE', ' On '):
            with self.subTest(value=value):
                self.assertIs(self.load({'DJANGO_ENV': 'development', 'DEBUG': value})['DEBUG'], True)
                with self.assertRaisesMessage(ImproperlyConfigured, 'DEBUG ei saa olla True tuotannossa.'):
                    self.load({**PROD, 'DEBUG': value})

    def test_debug_defaults_and_invalid_values(self):
        self.assertIs(self.load({})['DEBUG'], True)
        self.assertIs(self.load({k: v for k, v in PROD.items() if k != 'DEBUG'})['DEBUG'], False)
        for value in ('', 'maybe', '2', '"False"'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                self.load({**PROD, 'DEBUG': value})
