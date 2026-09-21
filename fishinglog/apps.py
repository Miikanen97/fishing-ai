from django.apps import AppConfig


class FishinglogConfig(AppConfig):
    name = 'fishinglog'

    def ready(self):
        from . import photo_signals
