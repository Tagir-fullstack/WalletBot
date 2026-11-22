import re
from decimal import Decimal, InvalidOperation


def parse_amount(text):
    value = text.strip().replace('\u00a0', '').replace(' ', '').replace(',', '.')
    if not re.fullmatch(r'\d{1,12}(?:\.\d{1,2})?', value):
        raise ValueError('Введите положительную сумму, максимум 2 знака после запятой. Например: 1250,50')
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Некорректная сумма') from exc
    if amount <= 0 or amount > Decimal('999999999999.99'):
        raise ValueError('Сумма должна быть больше нуля и не больше 999 999 999 999,99')
    return amount.quantize(Decimal('.01'))


def money(value):
    return f'{Decimal(value):,.2f}'.replace(',', ' ').replace('.', ',')
