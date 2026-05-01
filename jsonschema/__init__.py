"""Minimal local jsonschema compatibility layer.

This project uses only `Draft202012Validator(...).iter_errors(instance)` in
tests and benchmark helpers. We provide a tiny, dependency-free validator to
keep test collection runnable in constrained environments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass
class ValidationError:
    message: str
    path: list[Any]


class Draft202012Validator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema or {}

    def iter_errors(self, instance: Any) -> Iterable[ValidationError]:
        errors: list[ValidationError] = []
        self._validate(self.schema, instance, [], errors)
        return errors

    def _validate(self, schema: dict[str, Any], value: Any, path: list[Any], errors: list[ValidationError]) -> None:
        typ = schema.get("type")
        if isinstance(typ, str):
            if typ == "object" and not isinstance(value, dict):
                errors.append(ValidationError("is not of type 'object'", list(path)))
                return
            if typ == "array" and not isinstance(value, list):
                errors.append(ValidationError("is not of type 'array'", list(path)))
                return
            if typ == "string" and not isinstance(value, str):
                errors.append(ValidationError("is not of type 'string'", list(path)))
                return
            if typ == "number" and not isinstance(value, (int, float)):
                errors.append(ValidationError("is not of type 'number'", list(path)))
                return
            if typ == "integer" and not isinstance(value, int):
                errors.append(ValidationError("is not of type 'integer'", list(path)))
                return
            if typ == "boolean" and not isinstance(value, bool):
                errors.append(ValidationError("is not of type 'boolean'", list(path)))
                return

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            errors.append(ValidationError(f"{value!r} is not one of {enum_values!r}", list(path)))

        if isinstance(value, dict):
            required = schema.get("required")
            if isinstance(required, list):
                for key in required:
                    if key not in value:
                        errors.append(ValidationError(f"'{key}' is a required property", list(path)))
            props = schema.get("properties")
            if isinstance(props, dict):
                for key, subschema in props.items():
                    if key in value and isinstance(subschema, dict):
                        self._validate(subschema, value[key], path + [key], errors)
            pattern_props = schema.get("patternProperties")
            if isinstance(pattern_props, dict):
                # Lightweight: skip regex matching strictness, validate matching exact keys only when present.
                for pattern, subschema in pattern_props.items():
                    if not isinstance(subschema, dict):
                        continue
                    for key, subval in value.items():
                        try:
                            import re

                            if re.match(pattern, str(key)):
                                self._validate(subschema, subval, path + [key], errors)
                        except Exception:
                            continue

        if isinstance(value, list):
            items = schema.get("items")
            if isinstance(items, dict):
                for idx, item in enumerate(value):
                    self._validate(items, item, path + [idx], errors)

