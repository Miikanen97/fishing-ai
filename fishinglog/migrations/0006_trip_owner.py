from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def preserve_trips(apps, schema_editor):
    Trip = apps.get_model('fishinglog', 'Trip')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    alias = schema_editor.connection.alias
    trips = Trip.objects.using(alias).filter(owner__isnull=True)
    if not trips.exists():
        return
    username = 'fishingai_legacy'
    suffix = 0
    while User.objects.using(alias).filter(username=username).exists():
        suffix += 1
        username = f'fishingai_legacy_{suffix}'
    owner = User.objects.using(alias).create(username=username, password='!', is_active=False)
    trips.update(owner_id=owner.pk)


class Migration(migrations.Migration):
    dependencies = [
        ('fishinglog', '0005_separate_fishing_coordinates'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name='trip', name='owner', field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='fishing_trips', to=settings.AUTH_USER_MODEL, verbose_name='Omistaja')),
        migrations.RunPython(preserve_trips, migrations.RunPython.noop),
        migrations.AlterField(model_name='trip', name='owner', field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fishing_trips', to=settings.AUTH_USER_MODEL, verbose_name='Omistaja')),
    ]
