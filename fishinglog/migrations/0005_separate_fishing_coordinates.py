from django.db import migrations, models
from django.core.validators import MinValueValidator, MaxValueValidator

class Migration(migrations.Migration):
    dependencies = [('fishinglog', '0004_trip_latitude_trip_longitude_trip_wind_gust')]
    operations = [
        migrations.RenameField('trip', 'latitude', 'weather_latitude'),
        migrations.RenameField('trip', 'longitude', 'weather_longitude'),
        migrations.AlterField('trip', 'weather_latitude', models.DecimalField('Säähaun leveysaste',max_digits=8,decimal_places=5,null=True,blank=True,validators=[MinValueValidator(-90),MaxValueValidator(90)])),
        migrations.AlterField('trip', 'weather_longitude', models.DecimalField('Säähaun pituusaste',max_digits=8,decimal_places=5,null=True,blank=True,validators=[MinValueValidator(-180),MaxValueValidator(180)])),
        migrations.AddField('trip', 'latitude', models.DecimalField('Leveysaste',max_digits=8,decimal_places=5,null=True,blank=True,validators=[MinValueValidator(-90),MaxValueValidator(90)])),
        migrations.AddField('trip', 'longitude', models.DecimalField('Pituusaste',max_digits=8,decimal_places=5,null=True,blank=True,validators=[MinValueValidator(-180),MaxValueValidator(180)])),
    ]
