from django.core.management.base import BaseCommand, CommandError
from fishinglog.fishing_knowledge import load_knowledge, active_rules, KnowledgeValidationError


class Command(BaseCommand):
    help = 'Validoi paikallinen kalastustietopohja ilman verkkopyyntöjä tai AI-kutsuja.'

    def handle(self, *args, **options):
        try:
            bundle = load_knowledge()
            approved = active_rules(bundle)
        except KnowledgeValidationError as exc:
            raise CommandError(str(exc)) from exc
        total = sum(len(document['rules']) for document in bundle['rule_files'])
        self.stdout.write(self.style.SUCCESS(f'Tietopohja validoitu: {total} sääntöä, {len(approved)} aktiivista.'))
