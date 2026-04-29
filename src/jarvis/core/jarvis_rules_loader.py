"""JARVIS.md Loader for Jarvis Core Phase 1."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from .result import error_result, ok_result


class JarvisRulesLoader:
    """Load project-level JARVIS.md rules with tolerant parsing."""

    def load(self, project_root: str) -> dict:
        started = perf_counter()
        root = Path(project_root)
        if not root.exists() or not root.is_dir():
            return error_result(
                "REPO_INVALID_ROOT",
                f"Invalid project root: {project_root}",
                {"project_root": project_root},
                started,
            )

        jarvis_md = root / "JARVIS.md"
        if not jarvis_md.exists():
            return ok_result(
                self._empty_rules(rules_found=False),
                started,
            )

        try:
            text = jarvis_md.read_text(encoding="utf-8", errors="replace")
            parsed = self._parse_rules(text)
            normalized = self._validate_and_normalize(parsed)
            normalized["rules_found"] = True
            return ok_result(normalized, started)
        except Exception as exc:  # pragma: no cover - defensive
            # Malformed content should not crash the system.
            fallback = self._empty_rules(rules_found=True)
            self._warn(
                fallback["warnings"],
                kind="parse",
                code="RULE_PARSE_FAILED",
                severity="error",
                message=str(exc),
            )
            fallback["schema_valid"] = False
            return ok_result(fallback, started)

    def _parse_rules(self, text: str) -> dict:
        sections = {
            "architecture_rules": [],
            "coding_rules": [],
            "test_commands": [],
            "forbidden_actions": [],
        }
        current: str | None = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            lower = line.lower()
            if line.startswith("#"):
                if "architecture" in lower:
                    current = "architecture_rules"
                elif "coding" in lower or "code" in lower:
                    current = "coding_rules"
                elif "test" in lower:
                    current = "test_commands"
                elif "forbidden" in lower or "禁止" in lower:
                    current = "forbidden_actions"
                else:
                    current = None
                continue

            if line.startswith(("-", "*", "1.", "2.", "3.")):
                item = line.lstrip("-*0123456789. ").strip()
                if current and item:
                    sections[current].append(item)
                continue

            # Prefix-based fallback for loosely formatted files.
            if ":" in line:
                prefix, value = line.split(":", 1)
                p = prefix.strip().lower()
                v = value.strip()
                if p.startswith("test") and v:
                    sections["test_commands"].append(v)
                elif (p.startswith("forbidden") or "禁止" in p) and v:
                    sections["forbidden_actions"].append(v)
                elif p.startswith("architecture") and v:
                    sections["architecture_rules"].append(v)
                elif (p.startswith("coding") or p.startswith("code")) and v:
                    sections["coding_rules"].append(v)

        return sections

    def _validate_and_normalize(self, parsed: dict | None) -> dict:
        expected_fields = (
            "architecture_rules",
            "coding_rules",
            "test_commands",
            "forbidden_actions",
        )
        warnings: list[dict] = []
        raw = parsed if isinstance(parsed, dict) else {}
        if not isinstance(parsed, dict):
            self._warn(
                warnings,
                kind="schema",
                code="RULE_SCHEMA_NOT_OBJECT",
                severity="warn",
                message="parsed rules is not an object; fallback to defaults",
            )

        normalized: dict = {"rules_found": True, "warnings": warnings}
        for field in expected_fields:
            value = raw.get(field)
            normalized[field] = self._normalize_list_field(field, value, warnings)

        for key in raw.keys():
            if key not in expected_fields:
                self._warn(
                    warnings,
                    kind="unknown_field",
                    code="RULE_UNKNOWN_FIELD_IGNORED",
                    severity="info",
                    message=f"unknown field ignored: {key}",
                    details={"field": key},
                )

        normalized["schema_valid"] = not any(
            warning.get("kind") in {"schema", "parse"} for warning in warnings
        )
        return normalized

    def _normalize_list_field(self, field: str, value: object, warnings: list[dict]) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return self._normalize_list_items(field, value, warnings)
        if isinstance(value, str):
            self._warn(
                warnings,
                kind="schema",
                code="RULE_FIELD_COERCED_TO_LIST",
                severity="warn",
                message=f"{field} should be list, coerced from string",
                details={"field": field},
            )
            return self._normalize_list_items(field, [value], warnings)
        self._warn(
            warnings,
            kind="schema",
            code="RULE_FIELD_INVALID_TYPE",
            severity="warn",
            message=f"{field} has invalid type {type(value).__name__}, fallback to []",
            details={"field": field, "received_type": type(value).__name__},
        )
        return []

    def _normalize_list_items(self, field: str, values: list, warnings: list[dict]) -> list[str]:
        normalized: list[str] = []
        for item in values:
            if not isinstance(item, str):
                self._warn(
                    warnings,
                    kind="schema",
                    code="RULE_ITEM_IGNORED_NON_STRING",
                    severity="warn",
                    message=f"{field} item ignored (non-string: {type(item).__name__})",
                    details={"field": field, "received_type": type(item).__name__},
                )
                continue
            text = " ".join(item.strip().split())
            text = self._strip_wrapping_quotes(text)
            if text:
                normalized.append(text)
        return normalized

    def _empty_rules(self, rules_found: bool) -> dict:
        return {
            "rules_found": rules_found,
            "architecture_rules": [],
            "coding_rules": [],
            "test_commands": [],
            "forbidden_actions": [],
            "warnings": [],
            "schema_valid": True,
        }

    @staticmethod
    def _warn(
        warnings: list[dict],
        kind: str,
        code: str,
        severity: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        field = (details or {}).get("field")
        warnings.append(
            {
                "kind": kind,
                "severity": severity,
                "code": code,
                "message": message,
                "field": field,
                # Backward-compatible aliases for older consumers/tests.
                "category": kind,
                "details": details or {},
            }
        )

    @staticmethod
    def _strip_wrapping_quotes(text: str) -> str:
        value = text.strip()
        while len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1].strip()
        return value
