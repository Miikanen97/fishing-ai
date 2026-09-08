from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from .models import Trip, Catch, FishingProfile, AssistantUsage
from .test_catch_batch import trip_data


class AccountTests(TestCase):
    def setUp(self):
        self.password = 'Fishing-account-test-591!'
        self.user = get_user_model().objects.create_user('account-owner', email='before@example.com', password=self.password)
        self.other = get_user_model().objects.create_user('other-owner', email='private@example.com', password=self.password)
        self.trip = Trip.objects.create(owner=self.user, **trip_data())
        self.other_trip = Trip.objects.create(owner=self.other, **trip_data())
        Catch.objects.create(trip=self.trip, species='Ahven', time='12:00')
        Catch.objects.create(trip=self.other_trip, species='Kuha', time='12:00')
        FishingProfile.objects.create(user=self.user)
        AssistantUsage.objects.create(user=self.user)
        self.client.force_login(self.user)

    def test_profile_updates_only_email_for_session_user(self):
        response = self.client.get(reverse('account'))
        self.assertContains(response,'before@example.com')
        self.assertNotContains(response,'private@example.com')
        response = self.client.post(reverse('account'),{'email':'after@example.com','username':'hijack','id':self.other.pk,'is_superuser':'True'})
        self.assertRedirects(response,reverse('account'))
        self.user.refresh_from_db(); self.other.refresh_from_db()
        self.assertEqual(self.user.email,'after@example.com')
        self.assertEqual(self.user.username,'account-owner')
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.other.email,'private@example.com')
        self.assertEqual(self.client.post(reverse('account'),{'email':'invalid'}).status_code,200)
        self.assertEqual(self.client.get(f'/profiili/{self.other.pk}/').status_code,404)

    def test_password_change_preserves_session_and_rejects_bad_password(self):
        new = 'Changed-fishing-password-712!'
        data = {'old_password':'wrong','new_password1':new,'new_password2':new}
        self.assertEqual(self.client.post(reverse('password_change'),data).status_code,200)
        data['old_password']=self.password
        self.assertRedirects(self.client.post(reverse('password_change'),data),reverse('password_change_done'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertEqual(self.client.get(reverse('account')).status_code,200)
        self.assertTrue(self.other.check_password(self.password))

    def test_deletion_requires_post_confirmation_and_correct_password(self):
        url = reverse('delete_account')
        self.assertEqual(self.client.get(url).status_code,200)
        for data in ({}, {'password':self.password}, {'password':'wrong','confirm':'on'}):
            self.assertEqual(self.client.post(url,data).status_code,200)
            self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertRedirects(self.client.post(url,{'password':self.password,'confirm':'on','user':self.other.pk}),'/')
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Trip.objects.filter(pk=self.trip.pk).exists())
        self.assertFalse(Catch.objects.filter(trip_id=self.trip.pk).exists())
        self.assertFalse(FishingProfile.objects.filter(user_id=self.user.pk).exists())
        self.assertFalse(AssistantUsage.objects.filter(user_id=self.user.pk).exists())
        self.assertTrue(Trip.objects.filter(pk=self.other_trip.pk).exists())
        self.assertEqual(self.other_trip.catches.count(),1)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_login_and_csrf_protect_all_account_mutations(self):
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        for route in ('account','password_change','delete_account'):
            self.assertEqual(csrf.post(reverse(route)).status_code,403)
        self.client.logout()
        for route in ('account','password_change','password_change_done','delete_account'):
            self.assertEqual(self.client.get(reverse(route)).status_code,302)

    def test_admin_requires_permissions_and_lists_owners(self):
        self.assertEqual(self.client.get('/admin/').status_code,302)
        self.user.is_staff=True
        self.user.save()
        self.assertEqual(self.client.get('/admin/fishinglog/trip/').status_code,403)
        self.user.is_superuser=True
        self.user.save()
        for model in ('trip','catch','fishingprofile','assistantusage'):
            self.assertEqual(self.client.get('/admin/fishinglog/'+model+'/').status_code,200)
        self.assertContains(self.client.get('/admin/fishinglog/trip/'),'other-owner')
        self.assertEqual(self.client.get('/admin/auth/user/').status_code,200)
