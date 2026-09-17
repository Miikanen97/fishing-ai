"""Display-only formatting, independent of template tag discovery."""
from decimal import Decimal, InvalidOperation
from django.utils.formats import number_format

def measurement(value):
    if value is None:
        return ''
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return ''
        text = format(number, 'f')
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        return number_format(text, use_l10n=True)
    except (InvalidOperation, ValueError):
        return ''
