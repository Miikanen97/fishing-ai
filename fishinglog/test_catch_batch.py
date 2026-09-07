from .test_helpers import LoggedInMixin
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from .forms import CatchForm
from .models import Catch, Trip


def trip_data():
    return dict(date='2026-09-07', lake='Saimaa', location='Savonlinna',
                start_time='08:00', end_time='16:00', fishing_method='Jiggaus')


def fish(**changes):
    return dict(species='Ahven', length='0,45', weight='1,25', time='12:00', depth='4,5',
                lure_name='Jigi', lure_color='Vihreä', notes='Testikala', **changes)


def batch(*rows):
    return {'catches-TOTAL_FORMS': str(len(rows)), 'catches-INITIAL_FORMS': '0',
            **{f'catches-{i}-{key}': value for i, row in enumerate(rows) for key, value in row.items()}}


class CatchBatchTests(LoggedInMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.trip = Trip.objects.create(owner=self.user, **trip_data())
        self.url = reverse('fishinglog:catch_create', args=[self.trip.pk])

    def test_first_form_and_controls(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['formset'].forms), 1)
        for value in ['+ Lisää kala', 'Tallenna saaliit', 'Ei saalista', 'catches.js',
                      'name="catches-0-species"', 'id="fish-template"']:
            self.assertContains(response, value)

    def test_multiple_fish_with_comma_and_point(self):
        response = self.client.post(self.url, batch(fish(), {**fish(), 'species': 'Kuha', 'length': '0.525', 'weight': '1.501'}))
        self.assertRedirects(response, self.trip.get_absolute_url())
        first, second = self.trip.catches.order_by('pk')
        self.assertEqual(first.length, Decimal('0.450'))
        self.assertEqual(first.weight, Decimal('1.250'))
        self.assertEqual(first.depth, Decimal('4.5'))
        self.assertEqual(second.length, Decimal('0.525'))
        self.assertEqual(second.weight, Decimal('1.501'))
        self.assertContains(self.client.get(self.trip.get_absolute_url()), 'Pituus (m)')
        self.assertContains(self.client.get(self.trip.get_absolute_url()), 'Paino (kg)')

    def test_invalid_second_fish_saves_nothing_and_retains_values(self):
        response = self.client.post(self.url, batch(fish(), {**fish(), 'species': 'Kuha', 'weight': '-1'}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Catch.objects.exists())
        self.assertIn('weight', response.context['formset'].forms[1].errors)
        self.assertContains(response, 'value="Kuha"')
        self.assertContains(response, 'value="0,45"')

    def test_empty_batch_requires_fish_or_no_catch(self):
        for data in [batch(), batch({}), {}]:
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Catch.objects.exists())
            self.assertTrue(response.context['formset'].errors or response.context['formset'].non_form_errors())

    def test_untouched_extra_form_is_ignored(self):
        response = self.client.post(self.url, batch(fish(), {}))
        self.assertRedirects(response, self.trip.get_absolute_url())
        self.assertEqual(Catch.objects.count(), 1)

    def test_removed_middle_row_not_posted(self):
        # Browser renumbers the surviving forms before submission.
        response = self.client.post(self.url, batch(fish(), {**fish(), 'species': 'Kuha'}))
        self.assertRedirects(response, self.trip.get_absolute_url())
        self.assertEqual(list(Catch.objects.values_list('species', flat=True)), ['Ahven', 'Kuha'])

    def test_no_catch_ignores_unfilled_and_invalid_fish(self):
        response = self.client.post(self.url, {**batch({**fish(), 'weight': 'invalid'}), 'no_catch': 'on'})
        self.assertRedirects(response, self.trip.get_absolute_url())
        self.trip.refresh_from_db()
        self.assertTrue(self.trip.no_catch)
        self.assertFalse(Catch.objects.exists())
        self.assertContains(self.client.get(self.trip.get_absolute_url()), 'Ei saalista')
        self.assertContains(self.client.get(reverse('fishinglog:trip_list')), 'Ei saalista')

    def test_no_catch_without_any_form_management(self):
        self.assertRedirects(self.client.post(self.url, {'no_catch': 'on'}), self.trip.get_absolute_url())
        self.trip.refresh_from_db()
        self.assertTrue(self.trip.no_catch)

    def test_later_fish_clears_no_catch(self):
        self.trip.no_catch = True
        self.trip.save()
        self.assertRedirects(self.client.post(self.url, batch(fish())), self.trip.get_absolute_url())
        self.trip.refresh_from_db()
        self.assertFalse(self.trip.no_catch)
        self.assertEqual(self.trip.catches.count(), 1)

    def test_existing_fish_not_deleted_by_no_catch(self):
        self.client.post(self.url, batch(fish()))
        response = self.client.post(self.url, {'no_catch': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['outcome'].errors)
        self.assertEqual(self.trip.catches.count(), 1)
        self.trip.refresh_from_db()
        self.assertFalse(self.trip.no_catch)

    def test_trip_form_can_save_no_catch_and_clear_it(self):
        response = self.client.post(reverse('fishinglog:trip_create'), {**trip_data(), 'no_catch': 'on'})
        trip = Trip.objects.latest('pk')
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertTrue(trip.no_catch)
        self.assertFalse(trip.catches.exists())
        self.client.post(reverse('fishinglog:trip_update', args=[trip.pk]), trip_data())
        trip.refresh_from_db()
        self.assertFalse(trip.no_catch)

    def test_trip_form_rejects_conflicting_outcome(self):
        self.client.post(self.url, batch(fish()))
        response = self.client.post(reverse('fishinglog:trip_update', args=[self.trip.pk]), {**trip_data(), 'no_catch': 'on'})
        self.assertIn('no_catch', response.context['form'].errors)
        self.assertEqual(self.trip.catches.count(), 1)

    def test_edit_existing_catch_with_comma(self):
        self.client.post(self.url, batch(fish()))
        catch = Catch.objects.get()
        self.assertRedirects(self.client.post(reverse('fishinglog:catch_update', args=[self.trip.pk, catch.pk]),
                                             {**fish(), 'length': '0,555', 'weight': '2,125'}), self.trip.get_absolute_url())
        catch.refresh_from_db()
        self.assertEqual(catch.length, Decimal('0.555'))
        self.assertEqual(catch.weight, Decimal('2.125'))

    def test_negative_and_overprecise_numbers(self):
        for field, value in [('length', '-0,1'), ('weight', '-1,25'), ('weight', '1,2345'), ('length', '0,1234')]:
            form = CatchForm({**fish(), field: value})
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)

    def test_missing_measurements_remain_null(self):
        form = CatchForm({**fish(), 'length': '', 'weight': ''})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['length'])
        self.assertIsNone(form.cleaned_data['weight'])

    def test_batch_csrf_and_unknown_trip(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url, batch(fish())).status_code, 403)
        self.assertEqual(self.client.post(reverse('fishinglog:catch_create', args=[99999]), batch(fish())).status_code, 404)

    def test_atomic_save_on_database_error(self):
        original_save = Catch.save
        calls = 0
        def save(instance, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise IntegrityError('test failure')
            return original_save(instance, *args, **kwargs)
        with patch.object(Catch, 'save', save), self.assertRaises(IntegrityError):
            self.client.post(self.url, batch(fish(), fish()))
        self.assertFalse(Catch.objects.exists())

    def test_excessive_form_count_returns_validation_error(self):
        response = self.client.post(self.url, {'catches-TOTAL_FORMS': '1001', 'catches-INITIAL_FORMS': '0'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['formset'].non_form_errors())
        self.assertFalse(Catch.objects.exists())


class CatchUnitMigrationTests(TransactionTestCase):
    old = [('fishinglog', '0002_trip_air_pressure_trip_cloud_cover_and_more')]
    new = [('fishinglog', '0003_trip_no_catch_alter_catch_length_alter_catch_weight')]

    def test_existing_values_nulls_and_zero_are_converted_once(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.old)
        try:
            apps = executor.loader.project_state(self.old).apps
            old_trip = apps.get_model('fishinglog', 'Trip').objects.create(**trip_data())
            OldCatch = apps.get_model('fishinglog', 'Catch')
            entries = [('45.0', 1250), ('52.5', 1501), (None, None), ('0.0', 0), ('999999.9', 2147483647)]
            ids = [OldCatch.objects.create(trip=old_trip, species='Kuha', time='12:00', length=length, weight=weight).pk
                   for length, weight in entries]
            executor = MigrationExecutor(connection)
            executor.migrate(self.new)
            apps = executor.loader.project_state(self.new).apps
            NewCatch = apps.get_model('fishinglog', 'Catch')
            expected = [('0.450', '1.250'), ('0.525', '1.501'), (None, None), ('0.000', '0.000'), ('9999.999', '2147483.647')]
            for pk, (length, weight) in zip(ids, expected):
                obj = NewCatch.objects.get(pk=pk)
                self.assertEqual(obj.length, Decimal(length) if length is not None else None)
                self.assertEqual(obj.weight, Decimal(weight) if weight is not None else None)
            self.assertFalse(apps.get_model('fishinglog', 'Trip').objects.get(pk=old_trip.pk).no_catch)
            MigrationExecutor(connection).migrate(self.new)
            self.assertEqual(NewCatch.objects.get(pk=ids[0]).length, Decimal('0.450'))
            executor = MigrationExecutor(connection)
            executor.migrate(self.old)
            OldCatch = executor.loader.project_state(self.old).apps.get_model('fishinglog', 'Catch')
            self.assertEqual(OldCatch.objects.get(pk=ids[0]).length, Decimal('45.0'))
            self.assertEqual(OldCatch.objects.get(pk=ids[0]).weight, 1250)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

