from .Rules import required
from .Rules import string
from .Rules import number
from .Rules import regex
from .Rules import nullable
import re


class Validator:
    def exec(self, data: dict, rules: dict) -> dict:
        result = {}

        if not isinstance(data, dict) or not isinstance(rules, dict):
            raise ValueError('data or rules is not a dict type')

        for key, ruleSet in rules.items():
            value = data.get(key)

            for rule in ruleSet.split('|'):
                match = re.match(r'^(?P<name>\w+)(:)?(?(2)(?P<args>.+)|)$', rule, re.I | re.U)

                name = match.group('name')
                args = match.group('args')

                if name == 'nullable':
                    if nullable(value):
                        break
                elif name == 'required':
                    required(value, key)
                elif name == 'number':
                    value = number(value, key)
                elif name == 'string':
                    value = string(value, key)
                elif name == 'regex':
                    value = regex(value, key, args)
                else:
                    raise NameError('Call to undefined validation rule')

            result[key] = value

        return result
