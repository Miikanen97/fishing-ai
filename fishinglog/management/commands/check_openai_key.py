from django.core.management.base import BaseCommand
from fishinglog.assistant import api_key_configured


class Command(BaseCommand):
    help = 'Näytä vain, löytyykö OPENAI_API_KEY tästä prosessista. Ei API-kutsua.'

    def handle(self, *args, **options):
        self.stdout.write('OPENAI_API_KEY löytyi: ' + ('kyllä' if api_key_configured() else 'ei'))
