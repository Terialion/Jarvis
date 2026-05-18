"""ExplicitSkillInvocationResolver — detect when user names a skill directly."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

InvocationSource = Literal["explicit_name", "slash_command", "loaded_skill_followup", "none"]


@dataclass
class SkillInvocationRequest:
    matched: bool
    requested_skill: str | None = None
    resolved_skill: str | None = None
    raw_skill_mention: str | None = None
    user_instruction: str = ""
    action: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    source: InvocationSource = "none"
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "requested_skill": self.requested_skill,
            "resolved_skill": self.resolved_skill,
            "raw_skill_mention": self.raw_skill_mention,
            "user_instruction": self.user_instruction,
            "action": self.action,
            "arguments": self.arguments,
            "source": self.source,
            "confidence": self.confidence,
            "reason": self.reason,
        }


# Patterns for explicit skill naming in Chinese and English
_EXPLICIT_NAME_PATTERNS = [
    re.compile(r"使用\s+([a-zA-Z0-9_-]+)\s+skill", re.IGNORECASE),
    re.compile(r"用\s+([a-zA-Z0-9_-]+)\s+skill", re.IGNORECASE),
    re.compile(r"调用\s+([a-zA-Z0-9_-]+)\s+skill", re.IGNORECASE),
    re.compile(r"use\s+([a-zA-Z0-9_-]+)\s+skill", re.IGNORECASE),
    re.compile(r"run\s+([a-zA-Z0-9_-]+)\s+skill", re.IGNORECASE),
    re.compile(r"execute\s+([a-zA-Z0-9_-]+)\s+skill", re.IGNORECASE),
    re.compile(r"/skill\s+run\s+([a-zA-Z0-9_-]+)", re.IGNORECASE),
    re.compile(r"^/([a-zA-Z0-9_-]+)$", re.IGNORECASE),
]

_FOLLOWUP_PATTERNS = [
    "用这个skill",
    "用这个 skill",
    "用刚才那个skill",
    "用刚才那个 skill",
    "用它",
    "用那个skill",
    "用那个 skill",
    "use this skill",
    "use that skill",
    "use the skill",
    "用这个技能",
]

_ACTION_EXTRACTION = {
    "search": ["搜索", "search", "查找", "查询", "find"],
    "summarize": ["总结", "summarize", "摘要", "概括", "概述"],
    "analyze": ["分析", "analyze", "解析", "检查"],
    "run": ["运行", "run", "执行", "execute"],
    "fetch": ["抓取", "fetch", "获取", "下载", "爬取"],
    "create": ["创建", "create", "生成", "新建"],
    "fix": ["修复", "fix", "修理", "改正"],
    "test": ["测试", "test", "检验"],
    "review": ["审查", "review", "审阅", "检查"],
    "load": ["加载", "load", "载入"],
}


class SkillInvocationResolver:
    """Detects explicit skill invocation in user input."""

    def __init__(self) -> None:
        self._last_resolved: str | None = None
        self._last_referenced: str | None = None

    def resolve(
        self,
        text: str,
        available_names: list[str],
        *,
        last_loaded_skill: str | None = None,
        last_referenced_skill: str | None = None,
    ) -> SkillInvocationRequest:
        stripped = text.strip()
        lowered = stripped.lower()

        # 1. Check slash command /skill run <name>
        m = re.search(r"^/skill\s+run\s+([a-zA-Z0-9_-]+)", stripped, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            action, arguments, remaining = _extract_action_and_args(
                stripped[m.end():].strip(), name
            )
            return SkillInvocationRequest(
                matched=True,
                requested_skill=name,
                resolved_skill=_resolve_name(name, available_names),
                raw_skill_mention=m.group(0),
                user_instruction=remaining or stripped,
                action=action,
                arguments=arguments,
                source="slash_command",
                confidence=0.99,
                reason="slash_command",
            )

        # 2. Check bare slash command /<skill-name>
        m = re.match(r"^/([a-zA-Z0-9_-]+)$", stripped.strip())
        if m:
            name = m.group(1).strip()
            if name.lower() in {n.lower() for n in available_names}:
                return SkillInvocationRequest(
                    matched=True,
                    requested_skill=name,
                    resolved_skill=_resolve_name(name, available_names),
                    raw_skill_mention=m.group(0),
                    user_instruction=stripped,
                    source="slash_command",
                    confidence=0.95,
                    reason="bare_slash_command",
                )

        # 3. Check explicit name patterns
        for pattern in _EXPLICIT_NAME_PATTERNS:
            m = pattern.search(stripped)
            if m:
                name = m.group(1).strip()
                before = stripped[:m.start()].strip()
                after = stripped[m.end():].strip()
                remaining = f"{before} {after}".strip()
                action, arguments, remaining = _extract_action_and_args(remaining, name)
                resolved = _resolve_name(name, available_names)
                return SkillInvocationRequest(
                    matched=True,
                    requested_skill=name,
                    resolved_skill=resolved,
                    raw_skill_mention=m.group(0),
                    user_instruction=remaining or stripped,
                    action=action,
                    arguments=arguments,
                    source="explicit_name",
                    confidence=0.92 if resolved else 0.3,
                    reason="explicit_name_pattern" if resolved else "skill_not_found",
                )

        # 4. Check followup patterns
        is_followup = any(marker in lowered for marker in _FOLLOWUP_PATTERNS)
        if is_followup:
            ref = last_referenced_skill or last_loaded_skill
            if ref:
                self._last_resolved = ref
                return SkillInvocationRequest(
                    matched=True,
                    requested_skill=ref,
                    resolved_skill=_resolve_name(ref, available_names),
                    raw_skill_mention="followup",
                    user_instruction=stripped,
                    source="loaded_skill_followup",
                    confidence=0.85,
                    reason="followup_to_last_skill",
                )
            return SkillInvocationRequest(
                matched=True,
                requested_skill=None,
                resolved_skill=None,
                raw_skill_mention="followup",
                user_instruction=stripped,
                source="loaded_skill_followup",
                confidence=0.0,
                reason="ambiguous_skill_reference",
            )

        # 5. No match
        return SkillInvocationRequest(
            matched=False,
            user_instruction=stripped,
            source="none",
            confidence=0.0,
            reason="no_explicit_skill_mention",
        )

    def record_loaded(self, name: str) -> None:
        self._last_loaded = name

    def record_referenced(self, name: str) -> None:
        self._last_referenced = name


def _resolve_name(requested: str, available: list[str]) -> str | None:
    """Case-insensitive name resolution."""
    mapped = {n.lower(): n for n in available}
    return mapped.get(requested.lower())


def _extract_action_and_args(text: str, _skill_name: str) -> tuple[str | None, dict[str, Any], str]:
    """Extract action word and key=value arguments from skill invocation text."""
    if not text:
        return None, {}, ""
    lowered = text.lower()
    action = None
    for act, keywords in _ACTION_EXTRACTION.items():
        for kw in keywords:
            if kw in lowered:
                action = act
                break
        if action:
            break

    arguments: dict[str, Any] = {}
    remaining_parts: list[str] = []
    arg_pattern = re.compile(r"(\w+)\s*=\s*([一-鿿\w\-\./\?&=:]+)")
    last_end = 0
    for m in arg_pattern.finditer(text):
        arguments[m.group(1).strip()] = m.group(2).strip()
        remaining_parts.append(text[last_end:m.start()].strip())
        last_end = m.end()
    remaining_parts.append(text[last_end:].strip())
    remaining = " ".join(p for p in remaining_parts if p).strip()

    if not remaining and not arguments:
        remaining = text.strip()

    return action, arguments, remaining
