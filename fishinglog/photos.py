"""Private, normalized catch photos. Never expose storage URLs."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import logging
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 24_000_000


def storage_ready():
    if not settings.PRODUCTION:
        return True
    mount = settings.PRIVATE_MEDIA_VOLUME
    return bool(mount and Path(mount).is_absolute() and Path(mount).is_mount()
                and Path(settings.MEDIA_ROOT).resolve().is_relative_to(Path(mount).resolve()))


@deconstructible
class PrivatePhotoStorage(FileSystemStorage):
    def url(self, name):
        raise ValueError('Yksityisellä kuvalla ei ole julkista tiedosto-URLia.')

    def _save(self, name, content):
        if not storage_ready():
            raise ValidationError('Kuvien pysyvä tallennus ei ole käytössä. Tallenna saalis ilman kuvaa.')
        return super()._save(name, content)


def photo_name(instance, filename):
    return f'catches/{uuid4().hex}.jpg'


def normalize_photo(upload):
    if not storage_ready():
        raise ValidationError('Kuvien pysyvä tallennus ei ole käytössä. Tallenna saalis ilman kuvaa.')
    if getattr(upload, '_safe_photo', False):
        return upload
    if upload.size > MAX_BYTES:
        raise ValidationError('Kuvan enimmäiskoko on 8 Mt.')
    if Path(upload.name).suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise ValidationError('Valitse JPEG-, PNG- tai WebP-kuva.')
    try:
        upload.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(upload) as im:
                if im.format not in ('JPEG', 'PNG', 'WEBP') or im.width * im.height > MAX_PIXELS:
                    raise ValidationError('Kuva ei ole tuettu tai ylittää 24 megapikseliä.')
                im.verify()
            upload.seek(0)
            with Image.open(upload) as im:
                im.load()
                im = ImageOps.exif_transpose(im)
                im.thumbnail((1600, 1600))
                # Fresh pixels: no EXIF/GPS, comments, original filename or ICC metadata.
                clean = Image.new('RGB', im.size, 'white')
                if im.mode in ('RGBA', 'LA') or 'transparency' in im.info:
                    rgba = im.convert('RGBA')
                    clean.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    clean.paste(im.convert('RGB'))
                output = BytesIO()
                clean.save(output, format='JPEG', quality=85, optimize=True)
        result = ContentFile(output.getvalue(), name='photo.jpg')
        result._safe_photo = True
        return result
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('Tiedosto ei ole kelvollinen JPEG-, PNG- tai WebP-kuva.') from None


def remove_file(storage, name):
    if name:
        try:
            storage.delete(name)
        except OSError:
            logging.getLogger(__name__).warning('Private photo cleanup failed')
