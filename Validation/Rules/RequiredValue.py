from Exceptions import ValidationException


def required(field, key: str) -> None:
    if field is None:
        raise ValidationException(f'Field {key} must be not empty')
