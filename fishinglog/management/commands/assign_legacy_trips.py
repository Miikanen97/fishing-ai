from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from fishinglog.models import Trip


class Command(BaseCommand):
    help = 'Siirrä suljetun säilytystilin reissut nimetylle käyttäjälle.'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--from-user', default='fishingai_legacy')

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        try:
            target = User.objects.get(username=options['username'], is_active=True)
            source = User.objects.get(username=options['from_user'], is_active=False, password='!')
        except User.DoesNotExist as exc:
            raise CommandError('Aktiivista kohdekäyttäjää tai suljettua säilytystiliä ei löytynyt.') from exc
        if not source.username.startswith('fishingai_legacy'):
            raise CommandError('Lähdetilin pitää olla migraation säilytystili.')
        count = Trip.objects.filter(owner=source).update(owner=target)
        self.stdout.write(self.style.SUCCESS(f'Siirretty {count} reissua käyttäjälle {target.username}.'))
