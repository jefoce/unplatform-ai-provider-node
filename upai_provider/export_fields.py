"""Typed field readers for stored export JSON."""

from collections.abc import Mapping
from typing import cast


def _obj(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")

    return cast(Mapping[str, object], value)


def _str(obj: Mapping[str, object], name: str) -> str:
    value = obj.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    return value


def _optional_str(obj: Mapping[str, object], name: str) -> str | None:
    value = obj.get(name)
    if value is None:
        return None

    return _str(obj, name)


def _int(obj: Mapping[str, object], name: str) -> int:
    value = obj.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")

    return value


def _float(obj: Mapping[str, object], name: str) -> float:
    value = obj.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")

    return float(value)


def _bool(obj: Mapping[str, object], name: str, default: bool = False) -> bool:
    value = obj.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")

    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")

    return tuple(cast(list[str], value))


def _optional_strings(obj: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = obj.get(name)
    return () if value is None else _strings(value, name)


def _mapping(value: object, name: str) -> Mapping[str, object]:
    return _obj(value, name)


def _string_map(value: object, name: str) -> Mapping[str, str]:
    obj = _obj(value, name)
    return {key: _str(obj, key) for key in obj}
