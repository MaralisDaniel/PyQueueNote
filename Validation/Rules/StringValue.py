from Exceptions import ValidationException


def string(field, key: str) -> str:
    field_type = type(field)

    if field_type == str and not ("\n" in field):
        field = field.strip()

        if len(field) > 0:
            return field
    elif field_type == int or field_type == float:
        return str(field)

    raise ValidationException(f'Field {key} must be a non empty single line string')
