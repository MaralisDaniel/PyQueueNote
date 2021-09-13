import re
from Exceptions import ValidationException


def number(field, key: str) -> int:
    type_name = type(field)

    if type_name == int:
        return field
    elif type_name == str and re.fullmatch(r'-?\d+', field.strip()):
        return int(field)
    else:
        raise ValidationException(f'Field {key} must be a valid integer')
