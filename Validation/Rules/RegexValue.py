from Exceptions import ValidationException
import re


def regex(field, key: str, regular: str) -> str:
    field = str(field).strip()
    reg = re.match(r'^/(?P<pattern>.+)(/$)?(?(2)|/(?P<mods>[mixLusa]+))$', regular)

    if reg is not None:
        pattern = reg.group('pattern')
        mods = reg.group('mods')

        if mods:
            pattern = f"(?{mods})" + pattern

        if re.fullmatch(re.compile(pattern), field):
            return field

    raise ValidationException(f'Field {key} does not match the pattern')
