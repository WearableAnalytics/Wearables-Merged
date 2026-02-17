import re
import logging

logger = logging.getLogger(__name__)

def to_lower_case(value: str | int | float) -> str:
    return str(value).lower()

def replace(value: str | int | float, params: list[str]) -> str | int | float:

    value_as_string = str(value)

    replaced = re.sub(params[0], params[1], value_as_string)

    if type(value) is int:
        return int(replaced)
    elif type(value) is float:
        return float(replaced)

    return replaced

def append(value: str | int | float, params: list[str]):

    value_as_string = str(value)

    for p in params:
        value_as_string += p

    if value_as_string.isdigit() and type(value) is int:
        return int(value_as_string)
    elif value_as_string.isdecimal() and type(value) is float:
        return float(value_as_string)

    return value_as_string

def reverse_append(value: str | int | float, params: list[str]):
    value_as_string = str(value)

    suffix = ""

    for p in params:
        suffix += p

    value_as_string = value_as_string.removesuffix(suffix)

    if value_as_string.isdigit() and type(value) is int:
        return int(value_as_string)
    elif value_as_string.isdecimal() and type(value) is float:
        return float(value_as_string)

    return value_as_string


def prepend(value: str | int | float, params: list[str]):
    value_as_string = str(value)

    for p in params:
        value_as_string = p + value_as_string

    if value_as_string.isdigit() and type(value) is int:
        return int(value_as_string)
    elif value_as_string.isdecimal() and type(value) is float:
        return float(value_as_string)

    return value_as_string

def reverse_prepend(value: str | int | float, params: list[str]):
    value_as_string = str(value)

    prefix = ""

    for p in params:
        prefix += p

    logger.debug(f"prefix is {prefix}")

    value_as_string = value_as_string.removeprefix(prefix)

    if value_as_string.isdigit() and type(value) is int:
        return int(value_as_string)
    elif value_as_string.isdecimal() and type(value) is float:
        return float(value_as_string)

    return value_as_string

def substring(value: str | int | float, params: list[str]) -> str | int | float:
    value_as_string = str(value)

    start = int(params[0])
    end = int(params[1])

    new_value = value_as_string[start:end]

    if type(value) is int:
        return int(new_value)
    elif type(value) is float:
        return float(new_value)

    return new_value