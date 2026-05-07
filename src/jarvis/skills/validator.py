"""Static skill validation for strict and compatibility modes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any, Literal

from .loader import SkillLoader, SkillParseError
from .schema import SkillSpec

ValidationMode = Literal["compatibility", "strict"]

STRICT_REQUIRED_SECTIONS = (
    "When to use",
    "Do NOT use",
    "Inputs",
    "Workflow",
    "Decision Rules",
    "Safety Rules",
    "Output Format",
    "Failure Handling",
    "Examples",
)
SAFE_AUDIT_CONTEXT_HINTS = (
    "detect",
    "detection",
    "scan",
    "audit",
    "report",
    "must flag",
    "rule",
    "guideline",
    "indicator",
    "criteria",
    "pattern",
    "red flag",
    "signal",
    "validation",
    "local audit",
    "mode a",
    "mode b",
    "security declaration",
)
SECRET_PATTERNS = (
    r"\bsk-[A-Za-z0-9_-]{4,}\b",
    r"(?i)\bOPENAI_API_KEY\s*=",
    r"(?i)\bDEEPSEEK_API_KEY\s*=",
    r"(?i)\bJARVIS_LLM_API_KEY\s*=",
    r"(?i)\bAuthorization\s*:\s*Bearer\b",
    r"(?i)\bpassword\s*=",
    r"(?i)\btoken\s*=",
)
PROMPT_OVERRIDE_PATTERNS = (
    "ignore previous instructions",
    "system prompt override",
    "developer message override",
    "prompt injection",
    "jailbreak",
)
VALID_RISK_LEVELS = {"read_only", "write_approval_required", "command", "network", "credentialed", "unknown"}


@dataclass
class SkillValidationFinding:
    level: Literal["error", "warning", "info"]
    code: str
    message: str
    location: str | None = None
    recommendation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillValidationResult:
    ok: bool
    skill_name: str
    mode: str
    source: str
    findings: list[SkillValidationFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "skill_name": self.skill_name,
            "mode": self.mode,
            "source": self.source,
            "findings": [finding.to_dict() for finding in self.findings],
        }


class SkillValidator:
    def __init__(self, *, loader: SkillLoader | None = None) -> None:
        self.loader = loader or SkillLoader()

    def validate_spec(self, spec: SkillSpec, *, mode: ValidationMode = "strict") -> SkillValidationResult:
        body = self.loader.load_body(spec.path)
        findings: list[SkillValidationFinding] = []
        findings.extend(self._validate_common(spec, body, mode))
        findings.extend(self._validate_sections(spec, body, mode))
        findings.extend(self._validate_tools_and_risk(spec, body, mode))
        ok = not any(f.level == "error" for f in findings)
        return SkillValidationResult(ok=ok, skill_name=spec.name or "<unknown>", mode=mode, source=spec.source, findings=findings)

    def validate_path(
        self,
        path: str | Path,
        *,
        mode: ValidationMode = "strict",
        source: str = "external",
    ) -> SkillValidationResult:
        try:
            spec = self.loader.parse_skill_dir(path, source=source) if Path(path).is_dir() else self.loader.parse_skill_file(path, source=source)
        except SkillParseError as exc:
            return SkillValidationResult(
                ok=False,
                skill_name=Path(path).name,
                mode=mode,
                source=source,
                findings=[SkillValidationFinding(level="error", code="parse_error", message=str(exc), location=str(path))],
            )
        return self.validate_spec(spec, mode=mode)

    def validate_registry(self, specs: list[SkillSpec], *, mode_resolver: Any | None = None) -> list[SkillValidationResult]:
        results: list[SkillValidationResult] = []
        for spec in specs:
            mode = mode_resolver(spec) if callable(mode_resolver) else "strict"
            results.append(self.validate_spec(spec, mode=mode))
        return results

    def _validate_common(self, spec: SkillSpec, body: str, mode: ValidationMode) -> list[SkillValidationFinding]:
        findings: list[SkillValidationFinding] = []
        if not str(spec.name or "").strip():
            findings.append(self._finding("error", "missing_name", "Missing required frontmatter field `name`."))
        if not str(spec.description or "").strip():
            findings.append(self._finding("error", "missing_description", "Missing required frontmatter field `description`."))
        if ".." in Path(spec.path).parts:
            findings.append(self._finding("error", "path_traversal", "Path traversal is not allowed.", location=spec.path))
        findings.extend(self._find_secret_patterns(body, mode))
        findings.extend(self._find_prompt_override_indicators(body, mode))
        return findings

    def _validate_sections(self, spec: SkillSpec, body: str, mode: ValidationMode) -> list[SkillValidationFinding]:
        findings: list[SkillValidationFinding] = []
        sections = _extract_sections(body)
        if mode == "strict":
            for section in STRICT_REQUIRED_SECTIONS:
                if section.lower() not in sections:
                    findings.append(
                        self._finding(
                            "error",
                            "missing_required_section",
                            f"Missing required section `{section}`.",
                            location=spec.path,
                        )
                    )
        else:
            for section, code in (
                ("Safety Rules", "missing_safety_rules"),
                ("Failure Handling", "missing_failure_handling"),
                ("Output Format", "missing_output_format"),
            ):
                if section.lower() not in sections:
                    findings.append(self._finding("warning", code, f"Missing recommended section `{section}`.", location=spec.path))
        return findings

    def _validate_tools_and_risk(self, spec: SkillSpec, body: str, mode: ValidationMode) -> list[SkillValidationFinding]:
        findings: list[SkillValidationFinding] = []
        unknown_tokens = list((spec.metadata or {}).get("unknown_allowed_tools") or [])
        if not spec.raw_allowed_tools:
            level = "error" if mode == "strict" else "warning"
            findings.append(self._finding(level, "missing_allowed_tools", "No `allowed-tools` or `allowed_tools` declared.", location=spec.path))
        if unknown_tokens:
            level = "error" if mode == "strict" else "warning"
            findings.append(
                self._finding(
                    level,
                    "unknown_allowed_tool",
                    f"Unknown allowed tool(s): {', '.join(str(x) for x in unknown_tokens)}.",
                    location=spec.path,
                    recommendation="Use a registered Jarvis tool or declare ecosystem compatibility explicitly.",
                )
            )
        if spec.risk_level not in VALID_RISK_LEVELS:
            findings.append(self._finding("error", "invalid_risk_level", f"Invalid risk_level `{spec.risk_level}`.", location=spec.path))
        dangerous_tools = set(spec.allowed_tools) & {"file_editor.replace_text", "command_runner.run", "web_fetch"}
        if spec.risk_level == "read_only" and dangerous_tools:
            level = "error" if mode == "strict" else "warning"
            findings.append(
                self._finding(
                    level,
                    "risk_tool_mismatch",
                    f"`risk_level=read_only` conflicts with dangerous capabilities: {', '.join(sorted(dangerous_tools))}.",
                    location=spec.path,
                )
            )
        lowered_body = body.lower()
        needs_safety = bool(dangerous_tools) or any(token in lowered_body for token in ("curl ", "wget ", "authorization", "api key", "token", "password"))
        has_safety_section = "safety rules" in _extract_sections(body)
        if needs_safety and not has_safety_section:
            level = "error" if mode == "strict" else "warning"
            findings.append(
                self._finding(
                    level,
                    "missing_safety_rules_for_risky_skill",
                    "Risky command/write/network/credential behavior requires an explicit `Safety Rules` section.",
                    location=spec.path,
                )
            )
        if (Path(spec.path).parent / "scripts").exists() and "safety rules" not in _extract_sections(body):
            findings.append(
                self._finding(
                    "warning" if mode == "compatibility" else "error",
                    "scripts_without_safety_rules",
                    "Skill includes a `scripts/` directory but does not document Safety Rules.",
                    location=spec.path,
                )
            )
        if any((Path(spec.path).parent / name).exists() for name in ("package.json", "requirements.txt")) and "dependency" not in lowered_body:
            findings.append(
                self._finding(
                    "warning" if mode == "compatibility" else "info",
                    "missing_dependency_note",
                    "Skill package has dependency manifests but the SKILL.md does not mention dependency or setup notes.",
                    location=spec.path,
                )
            )
        if spec.risk_level_source == "unknown":
            findings.append(self._finding("warning", "missing_risk_level", "Risk level could not be inferred.", location=spec.path))
        return findings

    def _find_secret_patterns(self, body: str, mode: ValidationMode) -> list[SkillValidationFinding]:
        findings: list[SkillValidationFinding] = []
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, body):
                findings.append(
                    self._finding(
                        "error",
                        "hardcoded_secret_pattern",
                        "Potential hardcoded secret pattern found in skill content.",
                        recommendation="Remove the secret and replace it with a placeholder or local configuration reference.",
                    )
                )
                break
        return findings

    def _find_prompt_override_indicators(self, body: str, mode: ValidationMode) -> list[SkillValidationFinding]:
        findings: list[SkillValidationFinding] = []
        for line in body.splitlines():
            lowered = line.lower()
            for pattern in PROMPT_OVERRIDE_PATTERNS:
                if pattern in lowered and not any(hint in lowered for hint in SAFE_AUDIT_CONTEXT_HINTS):
                    findings.append(
                        self._finding(
                            "error" if mode == "compatibility" else "error",
                            "prompt_override_indicator",
                            f"Potential prompt override or jailbreak indicator detected: `{pattern}`.",
                        )
                    )
                    return findings
        if re.search(r"(?:\\u200b|\\u200c|\\u200d|\u200b|\u200c|\u200d)", body):
            findings.append(self._finding("error", "zero_width_hidden_instruction", "Zero-width characters detected in skill content."))
        if re.search(r"\b(?:aWdub3JlIHByZXZpb3VzIGluc3RydWN0aW9ucw==|c3lzdGVtIHByb21wdCBvdmVycmlkZQ==)\b", body):
            findings.append(self._finding("error", "encoded_override_indicator", "Encoded suspicious override text detected."))
        return findings

    @staticmethod
    def _finding(
        level: Literal["error", "warning", "info"],
        code: str,
        message: str,
        *,
        location: str | None = None,
        recommendation: str | None = None,
    ) -> SkillValidationFinding:
        return SkillValidationFinding(level=level, code=code, message=message, location=location, recommendation=recommendation)


def default_validation_mode_for_spec(spec: SkillSpec) -> ValidationMode:
    if spec.source in {"builtin", "user"}:
        return "strict"
    if spec.source in {"project", "env", "extra", "home"}:
        return "compatibility"
    if spec.source_format in {"skillhub", "ecosystem_markdown"}:
        return "compatibility"
    return "strict"


def _extract_sections(body: str) -> set[str]:
    sections: set[str] = set()
    for line in str(body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip().lower()
            if title:
                sections.add(title)
    return sections
