"""SkillDescriptionMatcher — match user requests to skills by metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .metadata import CapabilityIndex, SkillMetadata


@dataclass
class SkillMatchCandidate:
    name: str
    score: float
    reason: str
    matched_fields: list[str] = field(default_factory=list)
    skill_type: str = "unknown"
    executable: bool = False
    location: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "reason": self.reason,
            "matched_fields": self.matched_fields,
            "skill_type": self.skill_type,
            "executable": self.executable,
            "location": self.location,
        }


@dataclass
class SkillMatchResult:
    matched: bool
    selected_skill: str | None = None
    candidates: list[SkillMatchCandidate] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    needs_clarification: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "selected_skill": self.selected_skill,
            "candidates": [c.to_dict() for c in self.candidates[:5]],
            "confidence": self.confidence,
            "reason": self.reason,
            "needs_clarification": self.needs_clarification,
        }


# Weight multipliers for different match fields
_WEIGHTS = {
    "name": 4.0,
    "description": 2.5,
    "tags": 2.0,
    "capabilities": 2.5,
    "examples": 1.5,
    "when_to_use": 2.0,
}

# Chinese-English keyword mapping for common user intents
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "search": ["search", "搜索", "查找", "查询", "检索", "搜"],
    "news": ["news", "新闻", "最新", "today", "今天", "recent", "最近", "current", "当前"],
    "summary": ["summar", "总结", "摘要", "概括", "概述", "归纳"],
    "code": ["code", "代码", "编程", "programming", "开发", "generate"],
    "file": ["file", "文件", "管理", "manag", "organize"],
    "web": ["web", "网页", "fetch", "抓取"],
    "arxiv": ["arxiv", "论文", "paper", "学术", "research paper"],
    "github": ["github", "issue", "pr", "pull request", "repo"],
    "weather": ["weather", "天气", "气象"],
    "pdf": ["pdf", "文档", "document"],
    "newsletter": ["newsletter", "简报", "摘要"],
    "browser": ["browser", "浏览器", "playwright", "selenium"],
    "email": ["email", "邮件", "qq邮箱", "gmail"],
    "social": ["小红书", "xiaohongshu", "微博", "weibo", "social"],
    "ppt": ["ppt", "pptx", "演示", "presentation", "slides"],
    "docx": ["docx", "word", "文档"],
    "xlsx": ["xlsx", "excel", "表格", "spreadsheet"],
    "test": ["test", "测试", "检验"],
    "run": ["run", "运行", "执行", "execute"],
    "review": ["review", "审查", "审阅", "检查代码", "review code"],
    "fix": ["fix", "修复", "修理", "改正", "debug"],
}


class SkillDescriptionMatcher:
    """Match user request text to available skills by description, tags, and capabilities."""

    def __init__(self, *, ambiguity_threshold: float = 0.15, min_score: float = 0.25) -> None:
        self.ambiguity_threshold = ambiguity_threshold
        self.min_score = min_score

    def match(
        self,
        user_text: str,
        index: CapabilityIndex,
    ) -> SkillMatchResult:
        lowered = user_text.lower()
        entries = index.active_entries()
        if not entries:
            return SkillMatchResult(matched=False, reason="no_active_skills")

        candidates: list[SkillMatchCandidate] = []
        for entry in entries:
            score, matched_fields, reason_parts = self._score(entry, lowered)
            if score >= self.min_score:
                candidates.append(
                    SkillMatchCandidate(
                        name=entry.name,
                        score=score,
                        reason="; ".join(reason_parts) if reason_parts else f"score={score:.2f}",
                        matched_fields=matched_fields,
                        skill_type=entry.skill_type,
                        executable=entry.skill_type in ("executable", "hybrid"),
                        location=entry.location,
                    )
                )

        if not candidates:
            stripped_input = user_text.strip()
            # General chat / greeting / identity / capability questions are not skill requests
            if self._is_general_chat(stripped_input):
                return SkillMatchResult(matched=False, reason="general_chat_not_skill_request")
            # Short/vague inputs (≤5 chars) are inherently ambiguous even with no match
            if len(stripped_input) <= 5:
                return SkillMatchResult(
                    matched=True,
                    candidates=[],
                    confidence=0.0,
                    reason=f"ambiguous_short_input: '{stripped_input}' too vague for any skill",
                    needs_clarification=True,
                )
            return SkillMatchResult(matched=False, reason="no_skill_above_min_score")

        candidates.sort(key=lambda c: c.score, reverse=True)

        # Short/vague inputs (≤3 chars) are inherently ambiguous
        stripped_input = user_text.strip()
        if len(stripped_input) <= 3 and candidates:
            top = candidates[0]
            if top.score < 0.9:
                return SkillMatchResult(
                    matched=True,
                    candidates=candidates,
                    confidence=top.score,
                    reason=f"ambiguous_short_input: '{stripped_input}' too vague",
                    needs_clarification=True,
                )

        # Chinese vague suffixes ("一下", "一下a") suggest ambiguity even for longer inputs
        _CN_VAGUE_SUFFIXES = ["一下", "一下a", "一下a", "一下a", "吧"]
        if len(stripped_input) <= 6 and candidates:
            top = candidates[0]
            if any(stripped_input.endswith(s) for s in _CN_VAGUE_SUFFIXES) and top.score < 0.9:
                return SkillMatchResult(
                    matched=True,
                    candidates=candidates,
                    confidence=top.score,
                    reason=f"ambiguous_vague_input: '{stripped_input}' ends with vague suffix",
                    needs_clarification=True,
                )

        # If top candidate has high confidence and clear margin, auto-select
        top = candidates[0]
        if len(candidates) >= 2:
            second = candidates[1]
            gap = top.score - second.score
            if gap <= self.ambiguity_threshold and top.score < 0.7:
                return SkillMatchResult(
                    matched=True,
                    candidates=candidates,
                    confidence=top.score,
                    reason=f"ambiguous: {top.name}({top.score:.2f}) vs {second.name}({second.score:.2f})",
                    needs_clarification=True,
                )

        if top.score >= 0.6:
            return SkillMatchResult(
                matched=True,
                selected_skill=top.name,
                candidates=candidates,
                confidence=top.score,
                reason=top.reason,
            )

        return SkillMatchResult(
            matched=True,
            candidates=candidates,
            confidence=top.score,
            reason=f"low_confidence_top={top.name}({top.score:.2f})",
        )

    @staticmethod
    def _score(entry: SkillMetadata, lowered_text: str) -> tuple[float, list[str], list[str]]:
        total = 0.0
        matched_fields: list[str] = []
        reason_parts: list[str] = []

        # Name match
        name_lowered = entry.name.lower()
        name_tokens = set(re.split(r"[-_\s]+", name_lowered))
        text_tokens = set(re.split(r"[-_\s]+", lowered_text))
        name_overlap = name_tokens & text_tokens
        if name_overlap:
            w = _WEIGHTS["name"]
            total += w * len(name_overlap) / max(len(name_tokens), 1)
            matched_fields.append("name")
            reason_parts.append(f"name tokens matched: {name_overlap}")

        # Direct name mention
        if name_lowered in lowered_text:
            total += 2.0
            reason_parts.append("direct name mention")

        # Description match
        desc_lowered = entry.description.lower()
        desc_tokens = set(re.split(r"[\s,，、。；;:：()\[\]{}]+", desc_lowered))
        desc_tokens.discard("")
        desc_overlap = desc_tokens & text_tokens
        if desc_overlap:
            w = _WEIGHTS["description"]
            score = w * len(desc_overlap) / max(min(len(desc_tokens), 20), 1)
            total += score
            matched_fields.append("description")
            reason_parts.append(f"desc tokens: {desc_overlap}")

        # Tags match
        for tag in entry.tags:
            tag_lowered = tag.lower()
            if tag_lowered in lowered_text:
                total += _WEIGHTS["tags"]
                matched_fields.append("tags")
                reason_parts.append(f"tag matched: {tag}")
                break

        # Capabilities match
        for cap in entry.capabilities:
            cap_lowered = cap.lower()
            cap_tokens = set(re.split(r"[-_\s]+", cap_lowered))
            if cap_tokens & text_tokens or cap_lowered in lowered_text:
                total += _WEIGHTS["capabilities"]
                matched_fields.append("capabilities")
                reason_parts.append(f"cap matched: {cap}")
                break

        # Examples match
        for example in entry.examples:
            example_lowered = example.lower()
            if example_lowered in lowered_text:
                total += _WEIGHTS["examples"]
                matched_fields.append("examples")
                reason_parts.append(f"example matched: {example[:60]}")
                break

        # When-to-use match
        if entry.when_to_use:
            when_lowered = entry.when_to_use.lower()
            when_tokens = set(re.split(r"[\s,，、。]+", when_lowered))
            when_tokens.discard("")
            when_overlap = when_tokens & text_tokens
            if when_overlap:
                total += _WEIGHTS["when_to_use"] * len(when_overlap) / max(len(when_tokens), 1)
                matched_fields.append("when_to_use")
                reason_parts.append(f"when_to_use tokens: {when_overlap}")

        # Intent keyword bonus — match against skill name, description, capabilities, and tags
        for intent_cat, keywords in _INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw in lowered_text:
                    matched_intent = False
                    for cap in entry.capabilities:
                        if intent_cat in cap.lower():
                            total += 0.5
                            matched_fields.append("intent_keyword")
                            reason_parts.append(f"intent {intent_cat} -> cap {cap}")
                            matched_intent = True
                            break
                    for tag in entry.tags:
                        if intent_cat in tag.lower():
                            total += 0.3
                            matched_fields.append("intent_keyword")
                            reason_parts.append(f"intent {intent_cat} -> tag {tag}")
                            matched_intent = True
                            break
                    # Fallback: check if keyword or intent category appears in skill name or description
                    if not matched_intent:
                        kw_in_name = kw in name_lowered or intent_cat in name_lowered
                        kw_in_desc = kw in desc_lowered or intent_cat in desc_lowered
                        if kw_in_name or kw_in_desc:
                            total += 0.35
                            matched_fields.append("intent_keyword")
                            reason_parts.append(f"intent {intent_cat} (kw={kw}) -> name/desc match")
                    break

        return total, list(set(matched_fields)), reason_parts

    @staticmethod
    def _is_general_chat(text: str) -> bool:
        """Check if input is a general chat/greeting/identity/capability question, not a skill request."""
        low = text.lower().strip()
        # Greetings
        if low in {
            "hi", "hello", "hey", "hey there",
            "good morning", "good afternoon", "good evening",
            "你好", "你好啊", "哈喽", "在吗",
            "早上好", "下午好", "晚上好", "中午好",
            "嗨", "嘿", "ciallo",
        }:
            return True
        # Identity questions
        if low in {"who are you", "what are you", "你是谁", "你是什么"}:
            return True
        # Capability questions
        if any(t in low for t in (
            "你能做什么", "你会做什么", "你能干嘛", "你会干嘛",
            "你能帮我什么", "你能帮我做什么", "你可以帮我干嘛",
            "你会什么", "你能编程吗", "你会写代码吗", "你会编程吗",
            "what can you do", "what u can do", "what can u do",
            "what are you able to do", "what can you help me with",
            "capabilities", "can you code",
        )):
            return True
        # Model/config questions
        if any(t in low for t in ("什么模型", "what model", "which model", "你是什么模型")):
            return True
        # Usage help
        if any(t in low for t in ("怎么让你改代码", "how can you modify code", "how do i ask you to change code")):
            return True
        # Simple thanks/acknowledgments
        if low in {"thanks", "thank you", "ok", "okay", "great", "谢谢", "多谢"}:
            return True
        return False
