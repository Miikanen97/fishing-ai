from io import StringIO
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.core.validators import validate_email
from .forms import RegistrationForm
from .account_views import AccountForm

class EmailTests(TestCase):
    def test_valid_addresses_across_forms_and_superuser(self):
        for i,email in enumerate(['testi_6@example.com','nimi@hotmail.com','nimi@gmail.com','nimi+test@example.com']):
            validate_email(email)
            form = RegistrationForm({'username':f'user{i}', 'email':email, 'password1':'Safe-test-pass-2948!', 'password2':'Safe-test-pass-2948!'})
            self.assertTrue(form.is_valid(),form.errors)
            user = form.save()
            self.assertEqual(user.email,email)
            profile = AccountForm({'email':email}, instance=user)
            self.assertTrue(profile.is_valid(),profile.errors)
            call_command('createsuperuser', username=f'admin{i}', email=email, interactive=False, stdout=StringIO())
            self.assertEqual(get_user_model().objects.get(username=f'admin{i}').email,email)

    def test_invalid_addresses_stay_invalid(self):
        user = get_user_model().objects.create_user('existing')
        for email in ['invalid', 'nimi@@hotmail.com', 'nimi hotmail.com', r'testi\\_6\\@example.com']:
            with self.assertRaises(ValidationError): validate_email(email)
            form = RegistrationForm({'username':'new','email':email,'password1':'Safe-test-pass-2948!','password2':'Safe-test-pass-2948!'})
            self.assertFalse(form.is_valid())
            self.assertIn('email', form.errors)
            self.assertFalse(AccountForm({'email':email},instance=user).is_valid())
            with self.assertRaises(CommandError):
                call_command('createsuperuser',username='bad',email=email,interactive=False,stdout=StringIO())
