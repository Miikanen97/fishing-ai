from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import date, timedelta
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.conf import settings
from django.test import TestCase, override_settings
from django.template.loader import render_to_string
from django.urls import reverse
from .models import Catch, Trip
from .photos import MAX_BYTES, PrivatePhotoStorage
from .records import monthly_top
from .test_catch_batch import trip_data, fish, batch


def picture(name='test.jpg', size=(30, 20), fmt='JPEG'):
    out = BytesIO()
    im = Image.new('RGB', size, 'green')
    exif = Image.Exif(); exif[270] = 'PRIVATE GPS 62.12345,26.12345'
    im.save(out, format=fmt, exif=exif)
    return SimpleUploadedFile(name, out.getvalue(), content_type='image/jpeg')


class PhotoTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        config = override_settings(MEDIA_ROOT=temp.name, PRODUCTION=False)
        config.enable(); self.addCleanup(config.disable)
        self.user = get_user_model().objects.create_user('photos')
        self.other = get_user_model().objects.create_user('other')
        self.client.force_login(self.user)
        self.trip = Trip.objects.create(owner=self.user, **trip_data())
        self.create_url = reverse('fishinglog:catch_create', args=[self.trip.pk])

    def create(self, photo=None):
        values = batch(fish())
        if photo:
            values['catches-0-photo'] = photo
        response = self.client.post(self.create_url, values)
        self.assertEqual(response.status_code, 302)
        return Catch.objects.latest('pk')

    def update(self, catch, **extra):
        return self.client.post(reverse('fishinglog:catch_update', args=[self.trip.pk, catch.pk]), {**fish(), **extra})

    def test_optional_photo_and_validated_image_batch(self):
        empty = self.create()
        self.assertFalse(empty.photo)
        catch = self.create(picture())
        self.assertTrue(catch.photo)
        self.assertNotIn('test', catch.photo.name)
        with Image.open(catch.photo.path) as im:
            self.assertEqual(im.format, 'JPEG')
            self.assertFalse(im.getexif())
        self.assertContains(self.client.get(self.trip.get_absolute_url()), reverse('fishinglog:catch_photo', args=[catch.pk]))
        edit = self.client.get(reverse('fishinglog:catch_update', args=[self.trip.pk, catch.pk]))
        self.assertContains(edit, 'Nykyinen kuva')
        self.assertContains(edit, 'multipart/form-data')

    def test_invalid_type_corruption_and_size(self):
        for upload in (SimpleUploadedFile('x.svg', b'<svg/>'),
                       SimpleUploadedFile('x.jpg', b'not a photo'),
                       SimpleUploadedFile('x.jpg', b'x'*(MAX_BYTES+1)),
                       picture(size=(5001, 5000))):
            with self.subTest(name=upload.name, size=upload.size):
                response = self.client.post(self.create_url, {**batch(fish()), 'catches-0-photo': upload})
                self.assertEqual(response.status_code, 200)
                self.assertIn('photo', response.context['formset'].forms[0].errors)
                self.assertFalse(Catch.objects.exists())

    def test_swap_clear_and_cleanup(self):
        catch = self.create(picture())
        old = catch.photo.path
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.update(catch, photo=picture('new.png', fmt='PNG')).status_code, 302)
        catch.refresh_from_db()
        self.assertFalse(Path(old).exists())
        self.assertNotEqual(catch.photo.path, old)
        old = catch.photo.path
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.update(catch, remove_photo='on').status_code, 302)
        catch.refresh_from_db()
        self.assertFalse(catch.photo)
        self.assertFalse(Path(old).exists())

    def test_invalid_replacement_preserves_original_and_no_edit_keeps_it(self):
        catch = self.create(picture()); old = catch.photo.name
        self.assertEqual(self.update(catch).status_code, 302)
        self.assertEqual(self.update(catch, photo=SimpleUploadedFile('bad.jpg', b'bad')).status_code, 200)
        catch.refresh_from_db()
        self.assertEqual(catch.photo.name, old)
        self.assertTrue(Path(catch.photo.path).exists())

    def test_private_image_and_no_raw_media_route(self):
        catch = self.create(picture())
        url = reverse('fishinglog:catch_photo', args=[catch.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\xff\xd8'))
        response.close()
        self.assertEqual(self.client.get('/private-media/'+catch.photo.name).status_code, 404)
        with self.assertRaises(ValueError):
            _ = catch.photo.url
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.update(catch, remove_photo='on').status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_cascade_removes_image(self):
        catch = self.create(picture()); path = catch.photo.path
        with self.captureOnCommitCallbacks(execute=True):
            self.user.delete()
        self.assertFalse(Path(path).exists())

    @override_settings(PRODUCTION=True, PRIVATE_MEDIA_VOLUME='')
    def test_production_without_volume_disables_upload_only(self):
        response = self.client.post(self.create_url, {**batch(fish()), 'catches-0-photo': picture()})
        self.assertContains(response, 'pysyvä tallennus ei ole käytössä')
        self.assertFalse(Catch.objects.exists())
        self.create()
        with self.assertRaises(ValidationError):
            PrivatePhotoStorage().save('unsafe.jpg', picture())

    def test_configured_directory_without_real_volume_still_rejected(self):
        with override_settings(PRODUCTION=True, PRIVATE_MEDIA_VOLUME=settings.MEDIA_ROOT):
            response = self.client.post(self.create_url, {**batch(fish()), 'catches-0-photo': picture()})
        self.assertContains(response, 'pysyvä tallennus ei ole käytössä')
        self.assertFalse(Catch.objects.exists())

    def test_real_mount_configuration_can_store(self):
        with override_settings(PRODUCTION=True, PRIVATE_MEDIA_VOLUME=settings.MEDIA_ROOT), patch('fishinglog.photos.Path.is_mount', return_value=True):
            catch = self.create(picture())
        self.assertTrue(Path(catch.photo.path).exists())

    def test_record_photos_render_and_catch_delete_cleans_file(self):
        catch = self.create(picture()); path = catch.photo.path
        response = self.client.get(reverse('fishinglog:statistics'))
        self.assertContains(response, reverse('fishinglog:catch_photo', args=[catch.pk]))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('fishinglog:catch_delete', args=[self.trip.pk, catch.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Path(path).exists())

    def test_photo_endpoint_handles_absent_file(self):
        catch = self.create()
        self.assertEqual(self.client.get(reverse('fishinglog:catch_photo', args=[catch.pk])).status_code, 404)
        catch.photo = 'catches/missing.jpg'; catch.save()
        self.assertEqual(self.client.get(reverse('fishinglog:catch_photo', args=[catch.pk])).status_code, 404)


class FishRecordTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('records2')
        self.other = get_user_model().objects.create_user('other-records')
        self.client.force_login(self.user)
        self.trip = Trip.objects.create(owner=self.user, **{**trip_data(), 'date': date(2026, 12, 20),
            'lake':'PRIVATE_LAKE', 'location':'PRIVATE_SPOT', 'latitude':'62.12345', 'longitude':'26.12345'})

    def catch(self, weight=None, length=None, species='Hauki', trip=None):
        return Catch.objects.create(trip=trip or self.trip, species=species, weight=weight, length=length, time='12:00')

    @patch('fishinglog.records.timezone.localdate', return_value=date(2026, 12, 25))
    def test_monthly_order_boundaries_privacy_and_ties(self, today):
        first = self.catch(4); tied = self.catch(4); third = self.catch(3)
        self.catch(2); self.catch()
        old = Trip.objects.create(owner=self.user, **{**trip_data(), 'date':date(2026,11,30)})
        next_month = Trip.objects.create(owner=self.user, **{**trip_data(), 'date':date(2027,1,1)})
        foreign = Trip.objects.create(owner=self.other, **{**trip_data(), 'date':date(2026,12,20)})
        for trip in (old, next_month, foreign):
            self.catch(99, species='EXCLUDED', trip=trip)
        rows = monthly_top(self.user)
        self.assertEqual([r['pk'] for r in rows], [first.pk, tied.pk, third.pk])
        html = render_to_string('fishinglog/monthly_top.html', {'monthly_top': rows})
        for secret in ('PRIVATE', '62.12345', '26.12345', 'EXCLUDED'):
            self.assertNotIn(secret, html)
        self.assertTrue(all(set(r)=={'pk','species','weight','length','date','photo'} for r in rows))
        response = self.client.get(reverse('fishinglog:home'))
        self.assertContains(response, 'Kuukauden 3 suurinta')
        self.assertEqual(len(response.context['monthly_top']), 3)

    @patch('fishinglog.records.timezone.localdate', return_value=date(2026, 12, 25))
    def test_empty_one_two_and_weightless(self, today):
        self.catch(length=1)
        self.assertEqual(monthly_top(self.user), [])
        self.catch(1)
        self.assertEqual(len(monthly_top(self.user)), 1)
        self.catch(2)
        self.assertEqual(len(monthly_top(self.user)), 2)

    def test_overall_species_records_and_ties(self):
        heavy = self.catch(4, .8)
        self.catch(4, .7)
        long = self.catch(2, 1.1, 'Kuha')
        othertrip = Trip.objects.create(owner=self.other, **trip_data())
        self.catch(100, 9, 'SECRET', othertrip)
        response = self.client.get(reverse('fishinglog:statistics'))
        self.assertEqual(response.context['overall']['heaviest'], heavy)
        self.assertEqual(response.context['overall']['longest'], long)
        records = {r['name']: r for r in response.context['records']}
        self.assertEqual(records['Hauki']['heaviest'], heavy)
        self.assertEqual(records['Kuha']['longest'], long)
        self.assertNotContains(response, 'SECRET')
        self.assertNotContains(response, 'PRIVATE_SPOT')
        self.assertNotContains(response, '62.12345')
        self.assertContains(response, '20.12.2026')
