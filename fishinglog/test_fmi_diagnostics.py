import io
import logging
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
import requests
from . import weather
from .assistant import log_weather_failure


@override_settings(DEBUG=False)
class FMIDiagnosticsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def response(self, status, body):
        response = MagicMock()
        response.status_code = status
        response.iter_content.return_value = [body]
        response.__enter__.return_value = response
        return response

    def test_request_timeout_is_safe_and_not_logged_twice(self):
        with patch('fishinglog.weather.requests.get', side_effect=requests.Timeout('SECRET https://host/?latlon=62,27')), patch('fishinglog.weather.monotonic', side_effect=[1, 3]), self.assertLogs('fishinglog.fmi', 'WARNING') as logs:
            with self.assertRaises(weather.WeatherError) as error:
                weather.download({'place': 'PRIVATE'})
            log_weather_failure(error.exception)
        self.assertEqual(len(logs.records), 1)
        self.assertIn('stage=wfs_request type=timeout', logs.output[0])
        self.assertIn('duration_ms=2000', logs.output[0])
        self.assertNotIn('SECRET', str(logs.output))
        self.assertNotIn('latlon', str(logs.output))
        self.assertIsNone(logs.records[0].exc_info)

    def test_http_status_and_timeout_configuration_preserved(self):
        with patch('fishinglog.weather.requests.get', return_value=self.response(503, b'PRIVATE')) as get, self.assertLogs('fishinglog.fmi', 'WARNING') as logs:
            with self.assertRaisesMessage(weather.WeatherError, 'Ilmatieteen laitoksen sääpalvelu ei vastaa. Yritä myöhemmin.'):
                weather.download({})
        self.assertIn('http_status=503', logs.output[0])
        self.assertNotIn('PRIVATE', str(logs.output))
        self.assertEqual(get.call_args.kwargs['timeout'], (5, 15))
        get.assert_called_once()

    def test_xml_exception_whitelist_and_request_metadata(self):
        for code, expected in [('InvalidParameterValue', 'InvalidParameterValue'), ('PRIVATE_SECRET', 'None')]:
            body = f'<ExceptionReport><Exception exceptionCode="{code}"><ExceptionText>PRIVATE 62,27 api-key</ExceptionText></Exception></ExceptionReport>'.encode()
            with patch('fishinglog.weather.requests.get', return_value=self.response(400, body)), self.assertLogs('fishinglog.fmi', 'WARNING') as logs:
                xml = weather.download({})
                self.assertIsInstance(xml, bytes)
                self.assertEqual(xml, body)
                with self.assertRaises(weather.WeatherError):
                    weather.parse_response(xml, timezone.now(), True)
            self.assertIn('stage=parse', logs.output[0])
            self.assertIn('http_status=400', logs.output[0])
            self.assertIn('fmi_code=' + expected, logs.output[0])
            self.assertNotIn('duration_ms=None', logs.output[0])
            for secret in ('PRIVATE', '62,27', 'api-key', 'ExceptionText'):
                self.assertNotIn(secret, str(logs.output))

    def test_location_status_and_invalid_xml(self):
        with patch('fishinglog.weather.requests.get', return_value=self.response(400, b'PRIVATE')), self.assertLogs('fishinglog.fmi', 'WARNING') as logs:
            with self.assertRaises(weather.WeatherError):
                weather.resolve_place('PRIVATE')
        self.assertIn('stage=location', logs.output[0])
        self.assertIn('http_status=400', logs.output[0])
        with self.assertLogs('fishinglog.fmi', 'WARNING') as logs:
            with self.assertRaises(weather.WeatherError):
                weather.parse_response(b'PRIVATE not XML', timezone.now(), True)
        self.assertIn('type=xml_error', logs.output[0])
        self.assertNotIn('PRIVATE', str(logs.output))

    def test_warning_reaches_configured_console_without_debug(self):
        logger = logging.getLogger('fishinglog.fmi')
        self.assertEqual(logger.level, logging.WARNING)
        self.assertFalse(logger.propagate)
        stream = io.StringIO()
        with patch.object(logger.handlers[0], 'stream', stream):
            weather.log_failure(weather.NoWeatherData('PRIVATE'))
        self.assertIn('type=no_data', stream.getvalue())
        self.assertNotIn('PRIVATE', stream.getvalue())
