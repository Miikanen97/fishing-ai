from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from .models import FishingSpot


class SpotTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('spot-owner')
        self.other = get_user_model().objects.create_user('other-spot-owner')
        self.client.force_login(self.user)
        self.other_spot = FishingSpot.objects.create(user=self.other,name='Private spot',latitude=62,longitude=26)
        self.data = {'name':'Oma paikka','latitude':'61.12345','longitude':'27.12345','notes':'Kivikko'}
        self.url = reverse('fishinglog:spots')

    def test_create_list_edit_delete_and_owner_forgery(self):
        self.assertRedirects(self.client.post(self.url,{**self.data,'user':self.other.pk}),self.url)
        spot = FishingSpot.objects.get(user=self.user)
        self.assertNotContains(self.client.get(self.url),'Private spot')
        self.assertContains(self.client.get(self.url),'Oma paikka')
        edit = reverse('fishinglog:spot_update',args=[spot.pk])
        self.assertContains(self.client.get(edit),'61.12345')
        self.client.post(edit,{**self.data,'name':'Uusi','user':self.other.pk})
        spot.refresh_from_db(); self.assertEqual(spot.name,'Uusi'); self.assertEqual(spot.user,self.user)
        delete = reverse('fishinglog:spot_delete',args=[spot.pk])
        self.assertContains(self.client.get(delete),'Vahvista poisto')
        self.assertTrue(FishingSpot.objects.filter(pk=spot.pk).exists())
        self.assertRedirects(self.client.post(delete),self.url)
        self.assertFalse(FishingSpot.objects.filter(pk=spot.pk).exists())
        self.assertTrue(FishingSpot.objects.filter(pk=self.other_spot.pk).exists())

    def test_foreign_ids_rejected_for_get_and_post(self):
        for route in ('spot_update','spot_delete'):
            for method in ('get','post'):
                self.assertEqual(getattr(self.client,method)(reverse('fishinglog:'+route,args=[self.other_spot.pk]),self.data).status_code,404)

    def test_auth_csrf_validation_and_safe_json(self):
        for values in ({'latitude':'91'}, {'longitude':'181'}, {'latitude':''}):
            self.assertEqual(self.client.post(self.url,{**self.data,**values}).status_code,200)
        self.assertFalse(FishingSpot.objects.filter(user=self.user).exists())
        self.client.post(self.url,{**self.data,'name':'</script><script>alert(1)</script>'})
        self.assertNotContains(self.client.get(self.url),'</script><script>alert(1)</script>')
        c=Client(enforce_csrf_checks=True); c.force_login(self.user)
        self.assertEqual(c.post(self.url,self.data).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code,302)
        self.assertEqual(self.client.post(self.url,self.data).status_code,302)

    def test_user_deletion_cascades_to_own_spots_only(self):
        FishingSpot.objects.create(user=self.user,**self.data)
        self.user.delete()
        self.assertEqual(FishingSpot.objects.count(),1)


class SpotProductionIconTests(TestCase):
    def test_manifest_icons_are_rendered_and_served_by_whitenoise(self):
        from tempfile import TemporaryDirectory
        from django.conf import settings
        from django.core.management import call_command
        from django.contrib.staticfiles.storage import staticfiles_storage
        from django.test import override_settings

        with TemporaryDirectory() as root, override_settings(
            DEBUG=False, STATIC_ROOT=root, SECURE_SSL_REDIRECT=False,
            STORAGES={**settings.STORAGES, 'staticfiles': {
                'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}},
            WHITENOISE_AUTOREFRESH=False, WHITENOISE_USE_FINDERS=False,
        ):
            call_command('collectstatic', interactive=False, verbosity=0)
            user = get_user_model().objects.create_user('production-icons')
            client = Client()
            client.force_login(user)
            response = client.get(reverse('fishinglog:spots'))
            self.assertEqual(response.status_code, 200)
            for filename, attribute in (
                ('marker-icon.png', 'icon-url'),
                ('marker-icon-2x.png', 'icon-retina-url'),
                ('marker-shadow.png', 'shadow-url'),
            ):
                url = staticfiles_storage.url('fishinglog/leaflet/images/' + filename)
                self.assertRegex(url, r'\.[a-f0-9]{12}\.png$')
                self.assertContains(response, f'data-{attribute}="{url}"')
                image = client.get(url)
                self.assertEqual(image.status_code, 200)
                self.assertEqual(image['Content-Type'], 'image/png')
                self.assertTrue(b''.join(image.streaming_content).startswith(b'\x89PNG\r\n\x1a\n'))
