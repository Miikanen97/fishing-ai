from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


def measurement(label):
    return models.DecimalField(label, max_digits=7, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])


class Trip(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='fishing_trips', verbose_name='Omistaja')
    date = models.DateField('Päivämäärä', default=timezone.localdate)
    lake = models.CharField('Järven nimi', max_length=150)
    location = models.CharField('Kalastuspaikka', max_length=200)
    start_time = models.TimeField('Aloitusaika')
    end_time = models.TimeField('Lopetusaika')
    weather = models.CharField('Sää', max_length=200, blank=True)
    weather_place = models.CharField('Säähaun paikka', max_length=200, blank=True)
    weather_source = models.CharField('Säähaun lähdetiedot', max_length=1000, blank=True)
    wind_speed = measurement('Tuulen nopeus (m/s)')
    wind_gust = measurement('Tuulenpuuskat (m/s)')
    latitude = models.DecimalField('Leveysaste', max_digits=8, decimal_places=5, null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField('Pituusaste', max_digits=8, decimal_places=5, null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    weather_latitude = models.DecimalField('Säähaun leveysaste', max_digits=8, decimal_places=5, null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    weather_longitude = models.DecimalField('Säähaun pituusaste', max_digits=8, decimal_places=5, null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    wind_direction = models.DecimalField('Tuulen suunta (°)', max_digits=4, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(360)])
    air_pressure = measurement('Ilmanpaine (hPa)')
    cloud_cover = models.DecimalField('Pilvisyys (%)', max_digits=4, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    precipitation = measurement('Sade tunnin aikana (mm)')
    air_temperature = models.DecimalField('Ilman lämpötila (°C)', max_digits=5, decimal_places=1, null=True, blank=True)
    water_temperature = models.DecimalField('Veden lämpötila (°C)', max_digits=5, decimal_places=1, null=True, blank=True)
    fishing_method = models.CharField('Kalastustapa', max_length=100)
    depth = measurement('Syvyys (m)')
    boat_speed = measurement('Veneen nopeus (km/h)')
    notes = models.TextField('Muistiinpanot', blank=True)
    no_catch = models.BooleanField('Ei saalista', default=False)

    class Meta:
        ordering = ['-date', '-start_time', '-pk']

    def __str__(self):
        return f'{self.lake} – {self.date:%d.%m.%Y}'

    def get_absolute_url(self):
        return reverse('fishinglog:trip_detail', args=[self.pk])

    @property
    def wind_compass(self):
        from .weather import compass
        return compass(self.wind_direction)


class Catch(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='catches')
    species = models.CharField('Kalalaji', max_length=100)
    length = models.DecimalField('Pituus (m)', db_column='length_m', max_digits=10, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(0)])
    weight = models.DecimalField('Paino (kg)', db_column='weight_kg', max_digits=13, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(0)])
    lure_name = models.CharField('Vieheen nimi', max_length=150, blank=True)
    lure_color = models.CharField('Vieheen väri', max_length=100, blank=True)
    time = models.TimeField('Kellonaika')
    depth = measurement('Syvyys (m)')
    notes = models.TextField('Vapaa muistiinpano', blank=True)

    class Meta:
        ordering = ['time', 'pk']

    def __str__(self):
        return self.species

