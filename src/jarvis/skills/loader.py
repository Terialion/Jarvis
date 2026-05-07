"""Load and normalize ecosystem-compatible SKILL.md files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schema import SkillSpec

TOOL_ALIAS_MAP: dict[str, list[str]] = {
    "read": ["repo_reader.read_file", "repo_reader.search_files"],
    "write": ["file_editor.replace_text"],
    "bash": ["command_runner.run"],
    "webfetch": ["web_fetch"],
}
RISK_ORDER = ("unknown", "read_only", "write_approval_required", "command", "network", "credentialed")


class SkillParseError(ValueError):
    """Raised when a SKILL.md file or its frontmatter cannot be parsed."""


class SkillLoader:
    def parse_skill_file(self, path: str | Path, *, source: str = "unknown") -> SkillSpec:
        file_path = Path(path).resolve()
        text = file_path.read_text(encoding="utf-8", errors="replace")
        metadata, body = self._split_frontmatter(text)
        external_metadata = self._load_sidecar_metadata(file_path.parent)
        return self._build_skill_spec(
            file_path=file_path,
            frontmatter=metadata,
            body=body,
            source=source,
            external_metadata=external_metadata,
        )

    def parse_skill_dir(self, path: str | Path, *, source: str = "unknown") -> SkillSpec:
        skill_dir = Path(path).resolve()
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            raise SkillParseError(f"missing SKILL.md: {skill_dir}")
        return self.parse_skill_file(skill_file, source=source)

    def load_body(self, path: str | Path) -> str:
        file_path = Path(path).resolve()
        return file_path.read_text(encoding="utf-8", errors="replace")

    def validate_readable(self, path: str | Path) -> None:
        file_path = Path(path).resolve()
        if not file_path.exists():
            raise SkillParseError(f"unreadable SKILL.md: {file_path}")
        _ = file_path.read_text(encoding="utf-8", errors="replace")

    def _build_skill_spec(
        self,
        *,
        file_path: Path,
        frontmatter: dict[str, Any],
        body: str,
        source: str,
        external_metadata: dict[str, Any],
    ) -> SkillSpec:
        name = str(frontmatter.get("name") or file_path.parent.name).strip()
        description = str(frontmatter.get("description") or "").strip()
        raw_allowed = frontmatter.get("allowed-tools", frontmatter.get("allowed_tools"))
        normalized_tools, normalization_meta = normalize_allowed_tools(raw_allowed)
        declared_risk = str(frontmatter.get("risk_level") or "").strip()
        inferred_risk = infer_risk_level(
            declared_risk=declared_risk,
            normalized_tools=normalized_tools,
            raw_allowed_tools=raw_allowed,
            body=body,
        )
        risk_level = declared_risk or inferred_risk or "unknown"
        risk_level_source = "declared" if declared_risk else ("inferred" if risk_level != "unknown" else "unknown")
        read_when = _ensure_list(frontmatter.get("read_when"))
        always_apply = bool(frontmatter.get("alwaysApply", frontmatter.get("always_apply", False)))
        merged_metadata = dict(frontmatter.get("metadata") or {})
        merged_metadata["allowed_tool_patterns"] = list(normalization_meta.get("allow_patterns") or [])
        merged_metadata["unknown_allowed_tools"] = list(normalization_meta.get("unknown_tokens") or [])
        merged_metadata["normalization_notes"] = list(normalization_meta.get("notes") or [])
        body_preview = "\n".join(body.strip().splitlines()[:8]).strip() or None
        source_format = infer_source_format(
            frontmatter=frontmatter,
            external_metadata=external_metadata,
        )
        return SkillSpec(
            name=name,
            description=description,
            path=str(file_path),
            source=source,
            source_format=source_format,
            allowed_tools=normalized_tools,
            raw_allowed_tools=raw_allowed,
            risk_level=risk_level,
            risk_level_source=risk_level_source,  # type: ignore[arg-type]
            read_when=read_when,
            always_apply=always_apply,
            metadata=merged_metadata,
            external_metadata=external_metadata,
            body_preview=body_preview,
        )

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        raw = str(text or "")
        if not raw.startswith("---\n"):
            return {}, raw
        end_marker = raw.find("\n---\n", 4)
        if end_marker < 0:
            raise SkillParseError("invalid YAML frontmatter: missing closing marker")
        head = raw[4:end_marker]
        body = raw[end_marker + 5 :]
        return SkillLoader._parse_frontmatter(head), body

    @staticmethod
    def _parse_frontmatter(block: str) -> dict[str, Any]:
        lines = block.splitlines()
        parsed, idx = _parse_mapping(lines, 0, 0)
        if idx < len(lines):
            trailing = "\n".join(lines[idx:]).strip()
            if trailing:
                raise SkillParseError("invalid YAML frontmatter: trailing content")
        return parsed

    @staticmethod
    def _load_sidecar_metadata(skill_dir: Path) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for filename in ("_meta.json", "_skillhub_meta.json"):
            path = skill_dir / filename
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                raise SkillParseError(f"invalid sidecar metadata: {path}") from exc
            if isinstance(payload, dict):
                out[filename] = payload
        return out


def normalize_allowed_tools(raw_value: Any) -> tuple[list[str], dict[str, Any]]:
    raw_tokens = _ensure_list(raw_value, split_commas=True)
    normalized: list[str] = []
    allow_patterns: list[str] = []
    unknown_tokens: list[str] = []
    notes: list[str] = []
    for token in raw_tokens:
        parsed = str(token).strip()
        if not parsed:
            continue
        match = re.fullmatch(r"([A-Za-z]+)\(([^)]+)\)", parsed)
        if match:
            base = match.group(1).strip()
            pattern = match.group(2).strip()
            mapped = TOOL_ALIAS_MAP.get(base.lower())
            if mapped:
                allow_patterns.append(pattern)
                normalized.extend(mapped)
                notes.append(f"pattern:{base}({pattern})")
            else:
                unknown_tokens.append(parsed)
            continue
        if "." in parsed:
            normalized.append(parsed)
            continue
        mapped = TOOL_ALIAS_MAP.get(parsed.lower())
        if mapped:
            normalized.extend(mapped)
        else:
            unknown_tokens.append(parsed)
    deduped = list(dict.fromkeys(normalized))
    return deduped, {
        "allow_patterns": allow_patterns,
        "unknown_tokens": unknown_tokens,
        "notes": notes,
    }


def infer_risk_level(
    *,
    declared_risk: str,
    normalized_tools: list[str],
    raw_allowed_tools: Any,
    body: str,
) -> str:
    if declared_risk:
        return declared_risk
    lowered_tools = {str(item).lower() for item in list(normalized_tools or [])}
    lowered_raw = " ".join(_ensure_list(raw_allowed_tools, split_commas=True)).lower()
    lowered_body = str(body or "").lower()

    if any(token in lowered_body for token in ("api key", "apikey", "token", "password", "authorization", "credential")):
        return "credentialed"
    if any(token in lowered_body for token in ("curl ", "wget ", "http://", "https://", "requests.", "webfetch")):
        return "network"
    if "command_runner.run" in lowered_tools or "test_runner.run_test" in lowered_tools or "bash" in lowered_raw:
        return "command"
    if "file_editor.replace_text" in lowered_tools:
        return "write_approval_required"
    if lowered_tools and lowered_tools.issubset({"repo_reader.read_file", "repo_reader.search_files"}):
        return "read_only"
    return "unknown"


def infer_source_format(*, frontmatter: dict[str, Any], external_metadata: dict[str, Any]) -> str:
    if external_metadata.get("_skillhub_meta.json"):
        return "skillhub"
    if any(key in frontmatter for key in ("allowed-tools", "read_when", "alwaysApply")):
        return "ecosystem_markdown"
    return "jarvis_markdown"


def _ensure_list(value: Any, *, split_commas: bool = False) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if split_commas and "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text] if text else []
    return [str(value).strip()]


def _count_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_mapping(lines: list[str], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    idx = index
    while idx < len(lines):
        raw_line = lines[idx]
        if not raw_line.strip():
            idx += 1
            continue
        current_indent = _count_indent(raw_line)
        if current_indent < indent:
            break
        if current_indent > indent:
            raise SkillParseError("invalid YAML frontmatter: unexpected indentation")
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            raise SkillParseError("invalid YAML frontmatter: list item at mapping root")
        if ":" not in stripped:
            raise SkillParseError("invalid YAML frontmatter: missing ':'")
        key, remainder = stripped.split(":", 1)
        key = key.strip()
        remainder = remainder.strip()
        idx += 1
        if remainder == "":
            next_idx = idx
            while next_idx < len(lines) and not lines[next_idx].strip():
                next_idx += 1
            if next_idx >= len(lines) or _count_indent(lines[next_idx]) <= current_indent:
                result[key] = []
                idx = next_idx
                continue
            if lines[next_idx].strip().startswith("- "):
                value, idx = _parse_list(lines, next_idx, current_indent + 2)
            else:
                value, idx = _parse_mapping(lines, next_idx, current_indent + 2)
            result[key] = value
            continue
        result[key] = _parse_scalar(remainder)
    return result, idx


def _parse_list(lines: list[str], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    idx = index
    while idx < len(lines):
        raw_line = lines[idx]
        if not raw_line.strip():
            idx += 1
            continue
        current_indent = _count_indent(raw_line)
        if current_indent < indent:
            break
        stripped = raw_line[current_indent:].strip()
        if current_indent != indent or not stripped.startswith("- "):
            break
        item_text = stripped[2:].strip()
        idx += 1
        if not item_text:
            items.append("")
            continue
        items.append(_parse_scalar(item_text))
    return items, idx


def _parse_scalar(text: str) -> Any:
    raw = text.strip()
    if raw.startswith("{") or raw.startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if re.fullmatch(r"-?\d+", raw):
        try:
            return int(raw)
        except ValueError:
            return raw
    if re.fullmatch(r"-?\d+\.\d+", raw):
        try:
            return float(raw)
        except ValueError:
            return raw
    return raw
