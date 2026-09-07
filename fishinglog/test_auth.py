from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from .models import Trip, Catch
from .test_catch_batch import trip_data, fish, batch


class OwnershipTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('owner', password='Fishing-test-8492!')
        self.other = get_user_model().objects.create_user('other')
        self.trip = Trip.objects.create(owner=self.owner, **trip_data())
        self.catch = Catch.objects.create(trip=self.trip, **{k: v.replace(',', '.') if k in ('length', 'weight', 'depth') else v for k, v in fish().items()})
        self.client.force_login(self.other)

    def routes(self):
        return [
            ('trip_detail', [self.trip.pk]), ('trip_update', [self.trip.pk]),
            ('trip_delete', [self.trip.pk]), ('catch_create', [self.trip.pk]),
            ('catch_update', [self.trip.pk, self.catch.pk]),
            ('catch_delete', [self.trip.pk, self.catch.pk]),
        ]

    def test_other_user_cannot_access_or_mutate_any_object_route(self):
        for name, args in self.routes():
            for method in ('get', 'post'):
                with self.subTest(route=name, method=method):
                    response = getattr(self.client, method)(reverse('fishinglog:' + name, args=args), {**trip_data(), **batch(fish()), 'no_catch': 'on'})
                    self.assertEqual(response.status_code, 404)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.owner, self.owner)
        self.assertFalse(self.trip.no_catch)
        self.assertEqual(self.trip.catches.count(), 1)

    def test_lists_and_counts_are_private(self):
        for route in ('home', 'trip_list'):
            response = self.client.get(reverse('fishinglog:' + route))
            self.assertEqual(list(response.context['trips']), [])
        response = self.client.get('/')
        self.assertEqual(response.context['trip_count'], 0)
        self.assertEqual(response.context['catch_count'], 0)
        self.client.logout()
        self.assertNotContains(self.client.get('/'), self.trip.lake)

    def test_anonymous_routes_require_login(self):
        self.client.logout()
        routes = self.routes() + [('trip_list', []), ('trip_create', []), ('weather_lookup', [])]
        for name, args in routes:
            methods = ('post',) if name == 'weather_lookup' else ('get', 'post')
            for method in methods:
                response = getattr(self.client, method)(reverse('fishinglog:' + name, args=args))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse('login') + '?next='))
        self.assertEqual(Trip.objects.count(), 1)
        self.assertEqual(Catch.objects.count(), 1)

    def test_owner_is_assigned_server_side(self):
        response = self.client.post(reverse('fishinglog:trip_create'), {**trip_data(), 'owner': self.owner.pk})
        self.assertEqual(response.status_code, 302)
        trip = Trip.objects.latest('pk')
        self.assertEqual(trip.owner, self.other)
        self.client.post(reverse('fishinglog:trip_update', args=[trip.pk]), {**trip_data(), 'owner': self.owner.pk})
        trip.refresh_from_db()
        self.assertEqual(trip.owner, self.other)

    def test_register_login_logout_and_invalid_credentials(self):
        self.client.logout()
        for route in ('login', 'register'):
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        data = {'username': 'new-fisher', 'password1': 'Fishing-test-8492!', 'password2': 'Fishing-test-8492!'}
        self.assertRedirects(self.client.post(reverse('register'), data), reverse('login'))
        self.assertEqual(self.client.post(reverse('register'), data).status_code, 200)
        self.assertEqual(self.client.post(reverse('login'), {'username': 'new-fisher', 'password': 'wrong'}).status_code, 200)
        self.assertRedirects(self.client.post(reverse('login'), {'username': 'new-fisher', 'password': data['password1'], 'next': 'https://example.com'}), '/')
        self.assertContains(self.client.get('/'), 'new-fisher')
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), '/')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_auth_post_csrf(self):
        client = Client(enforce_csrf_checks=True)
        for route in ('login', 'register', 'logout'):
            self.assertEqual(client.post(reverse(route)).status_code, 403)

    def test_legacy_transfer_command(self):
        legacy = get_user_model().objects.create(username='fishingai_legacy', password='!', is_active=False)
        self.trip.owner = legacy
        self.trip.save()
        call_command('assign_legacy_trips', self.owner.username, stdout=StringIO())
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.owner, self.owner)
        self.assertEqual(self.trip.catches.count(), 1)


class OwnershipMigrationTests(TransactionTestCase):
    def test_existing_trips_and_catches_are_preserved_on_inactive_account(self):
        old = [('fishinglog', '0005_separate_fishing_coordinates')]
        new = [('fishinglog', '0006_trip_owner')]
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            trip = apps.get_model('fishinglog', 'Trip').objects.create(**trip_data())
            catch = apps.get_model('fishinglog', 'Catch').objects.create(trip=trip, **{k: v.replace(',', '.') if k in ('length', 'weight', 'depth') else v for k, v in fish().items()})
            executor = MigrationExecutor(connection)
            executor.migrate(new)
            apps = executor.loader.project_state(new).apps
            saved = apps.get_model('fishinglog', 'Trip').objects.get(pk=trip.pk)
            self.assertFalse(saved.owner.is_active)
            self.assertEqual(saved.owner.password, '!')
            self.assertEqual(saved.lake, trip.lake)
            self.assertTrue(saved.catches.filter(pk=catch.pk).exists())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
