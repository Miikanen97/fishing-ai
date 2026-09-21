from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import Catch
from .photos import normalize_photo, remove_file


@receiver(pre_save, sender=Catch)
def prepare_photo(sender, instance, **kwargs):
    if kwargs.get('raw') or (kwargs.get('update_fields') is not None and 'photo' not in kwargs['update_fields']):
        return
    old = sender.objects.filter(pk=instance.pk).values_list('photo', flat=True).first() if instance.pk else ''
    instance._old_photo = old
    if instance.photo and not instance.photo._committed:
        instance.photo = normalize_photo(instance.photo.file)


@receiver(post_save, sender=Catch)
def replace_photo(sender, instance, **kwargs):
    if kwargs.get('raw') or (kwargs.get('update_fields') is not None and 'photo' not in kwargs['update_fields']):
        return
    old = getattr(instance, '_old_photo', '')
    if old and old != instance.photo.name:
        transaction.on_commit(lambda: remove_file(instance.photo.storage, old))


@receiver(post_delete, sender=Catch)
def delete_photo(sender, instance, **kwargs):
    name, storage = instance.photo.name, instance.photo.storage
    transaction.on_commit(lambda: remove_file(storage, name))
