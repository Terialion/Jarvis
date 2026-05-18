"""ReferenceSkillPlanner: translate SKILL.md guidance into tool call plans."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .schema import SkillSpec


@dataclass
class ReferenceSkillPlan:
    skill_name: str
    user_instruction: str
    extracted_arguments: dict[str, Any] = field(default_factory=dict)
    recommended_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "user_instruction": self.user_instruction,
            "extracted_arguments": self.extracted_arguments,
            "recommended_tool_calls": self.recommended_tool_calls,
            "rationale": self.rationale,
            "confidence": self.confidence,
        }


_CAP_TO_TOOL: dict[str, dict[str, Any]] = {
    "search": {"tool": "web.search", "default_args": {}, "description": "Search the web"},
    "multi-search": {"tool": "web.search", "default_args": {"engine": "multi"}, "description": "Multi-engine web search"},
    "news": {"tool": "web.search", "default_args": {"time_range": "week"}, "description": "Search for news"},
    "fetch": {"tool": "web.fetch", "default_args": {}, "description": "Fetch a web page"},
    "summary": {"tool": "agent.skill_run", "default_args": {"skill_name": "summarize"}, "description": "Summarize content"},
    "code generation": {"tool": "agent.skill_run", "default_args": {"skill_name": "code-generator"}, "description": "Generate code"},
    "file management": {"tool": "agent.skill_run", "default_args": {"skill_name": "file-manager"}, "description": "Manage files"},
    "arxiv": {"tool": "web.fetch", "default_args": {"url_template": "https://arxiv.org/search/?query={query}"}, "description": "Search arXiv papers"},
    "github": {"tool": "agent.skill_run", "default_args": {"skill_name": "github"}, "description": "GitHub operations"},
    "pdf": {"tool": "agent.skill_run", "default_args": {"skill_name": "pdf"}, "description": "PDF processing"},
    "docx": {"tool": "agent.skill_run", "default_args": {"skill_name": "docx"}, "description": "Word document processing"},
    "xlsx": {"tool": "agent.skill_run", "default_args": {"skill_name": "xlsx"}, "description": "Excel processing"},
    "pptx": {"tool": "agent.skill_run", "default_args": {"skill_name": "pptx"}, "description": "PowerPoint processing"},
    "weather": {"tool": "agent.skill_run", "default_args": {"skill_name": "weather"}, "description": "Weather information"},
}

_WRAPPER_PHRASES = [
    r"使用\s+\S+\s+skill\s*",
    r"用\s+\S+\s+skill\s*",
    r"调用\s+\S+\s+skill\s*",
    r"用这个\s*skill\s*",
    r"用这个\s*",
    r"use\s+\S+\s+skill\s*",
    r"run\s+\S+\s+skill\s*",
    r"help me\s*",
    r"please\s*",
    r"帮我\s*",
    r"请\s*",
]


class ReferenceSkillPlanner:
    """Translate reference-only skill metadata into deterministic tool call plans."""

    def plan(self, skill_spec: SkillSpec, user_instruction: str) -> ReferenceSkillPlan:
        primary_cap = self._primary_capability(skill_spec)
        tool_info = _CAP_TO_TOOL.get(primary_cap, {"tool": "web.search", "default_args": {}, "description": "Default search"})

        cleaned_query = self._extract_query(user_instruction, skill_spec.name)
        args = dict(tool_info["default_args"])
        if tool_info["tool"] in ("web.search", "web.fetch"):
            args["query"] = cleaned_query
            args["guided_by_skill"] = skill_spec.name
            args["invocation_path"] = "reference_skill_guided_tool_call"
            args["source"] = "skill_guided"
        else:
            args["user_instruction"] = cleaned_query

        tool_calls = [
            {
                "tool": tool_info["tool"],
                "arguments": args,
                "guided_by_skill": skill_spec.name,
                "skill_type": "reference",
            }
        ]
        rationale = (
            f"Reference skill '{skill_spec.name}' (type={skill_spec.skill_type}, primary_cap={primary_cap}) "
            f"guides tool call to {tool_info['tool']}. "
            f"Original user instruction normalized to query: '{cleaned_query[:120]}'. "
            "Skill is reference-only; tool call follows SKILL.md guidance, not skill.run."
        )
        return ReferenceSkillPlan(
            skill_name=skill_spec.name,
            user_instruction=user_instruction,
            extracted_arguments=args,
            recommended_tool_calls=tool_calls,
            rationale=rationale,
            confidence=0.8 if primary_cap in _CAP_TO_TOOL else 0.5,
        )

    @staticmethod
    def _primary_capability(skill_spec: SkillSpec) -> str:
        if skill_spec.capabilities:
            return skill_spec.capabilities[0]
        tag_cap_map = {
            "search": "search",
            "news": "news",
            "summary": "summary",
            "code": "code generation",
            "file": "file management",
            "web": "fetch",
            "arxiv": "arxiv",
            "github": "github",
            "pdf": "pdf",
            "weather": "weather",
        }
        for tag in skill_spec.tags:
            lower = tag.lower()
            for key, cap in tag_cap_map.items():
                if key in lower:
                    return cap
        name_lower = skill_spec.name.lower()
        for key, cap in tag_cap_map.items():
            if key in name_lower:
                return cap
        return "search"

    @staticmethod
    def _extract_query(text: str, skill_name: str) -> str:
        cleaned = str(text or "").strip()
        for pattern in _WRAPPER_PHRASES:
            cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        quoted = re.findall(r'["“”](.+?)["“”]', cleaned)
        if quoted:
            return quoted[0].strip()

        cleaned = re.sub(rf"\b{re.escape(skill_name.lower())}\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(搜索|查找|查询|帮我|请|麻烦|需要|想要|要)\s*", "", cleaned).strip()
        if not cleaned:
            cleaned = str(text or "").strip()
        return cleaned[:500]

