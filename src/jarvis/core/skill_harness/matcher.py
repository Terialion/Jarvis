"""Rule-first skill matcher."""

from __future__ import annotations

from time import perf_counter

from ..result import ok_result
from .models import SkillMatch


class SkillMatcher:
    def match_skills(
        self,
        task_input: str,
        context: dict | None,
        available_tools: list[str],
        available_skills: list[dict],
        pre_routing_hints: dict | None = None,
    ) -> dict:
        started = perf_counter()
        text = (task_input or "").lower()
        context_text = " ".join(str(v).lower() for v in (context or {}).values())
        tool_set = set(available_tools or [])
        hints = pre_routing_hints or {}
        seeded = set(str(item) for item in list(hints.get("attached_default_skills") or []))
        preferred = set(str(item) for item in list((hints.get("planner_hints") or {}).get("skill_preferences") or []))
        policy_bias = set(str(item).lower() for item in list(hints.get("selected_policies") or []))
        planner_hints = hints.get("planner_hints") or {}
        task_shape = str(planner_hints.get("task_shape") or "")
        runtime_feedback = hints.get("runtime_feedback") or {}
        prefer_safe_skills = bool(runtime_feedback.get("prefer_safe_skills"))
        last_failure = str(runtime_feedback.get("last_failure_type") or "")
        matched: list[SkillMatch] = []
        rejected: list[dict] = []
        selection_reasons: list[str] = []
        seed_sources: dict[str, list[str]] = {}

        for skill in available_skills:
            skill_id = str(skill.get("skill_id") or "")
            tags = [str(tag).lower() for tag in list(skill.get("tags") or [])]
            required = set(skill.get("required_tools") or [])
            reasons: list[str] = []
            score = float(skill.get("priority_hint") or 0.0)
            if skill.get("status") != "enabled":
                rejected.append({"skill_id": skill_id, "reasons": ["skill_disabled"]})
                continue
            if required and not required.issubset(tool_set):
                rejected.append(
                    {
                        "skill_id": skill_id,
                        "reasons": ["required_tools_missing"],
                        "missing_tools": sorted(required - tool_set),
                    }
                )
                continue
            for tag in tags:
                if tag and (tag in text or tag in context_text):
                    score += 0.8
                    reasons.append(f"tag_match:{tag}")
            name = str(skill.get("skill_name") or "").lower()
            if name and name in text:
                score += 1.0
                reasons.append("name_match")
            if not reasons:
                score += 0.1
                reasons.append("default_candidate")
            if skill_id in seeded:
                score += 2.0
                reasons.append("seeded_by_policy")
                seed_sources.setdefault(skill_id, []).append("policy_seed")
            if skill_id in preferred:
                score += 1.0
                reasons.append("planner_preference")
                seed_sources.setdefault(skill_id, []).append("planner_preference")
            if "structured-reasoning" in policy_bias and "reasoning" in tags:
                score += 0.6
                reasons.append("policy_bias:structured-reasoning")
            if "safe-action-guard" in policy_bias and "safe" in tags:
                score += 0.6
                reasons.append("policy_bias:safe-action-guard")
            if task_shape in {"multi_step", "cross_domain"} and "reasoning" in tags:
                score += 0.5
                reasons.append("task_shape:multi_step_bias")
            if prefer_safe_skills and "safe" in tags:
                score += 0.8
                reasons.append("runtime_feedback:prefer_safe")
            if last_failure in {"test_failed_requires_patch", "test_assertion_failure"} and "test" in tags:
                score += 0.4
                reasons.append("runtime_feedback:test_failure_bias")
            matched.append(SkillMatch(skill_id=skill_id, score=score, reasons=reasons))

        matched.sort(key=lambda item: (-item.score, item.skill_id))
        if seeded:
            selection_reasons.append("used_policy_seed")
        if preferred:
            selection_reasons.append("used_planner_preference")
        if prefer_safe_skills:
            selection_reasons.append("used_runtime_safe_preference")
        selected_ids = [item.skill_id for item in matched]
        effective_skill_hits = [item.skill_id for item in matched if item.score >= 1.5]
        ineffective_skill_hits = [item.skill_id for item in matched if item.score < 0.5]
        return ok_result(
            {
                "matched_skills": [item.to_dict() for item in matched],
                "rejected_skills": rejected,
                "ranking": [item.skill_id for item in matched],
                "score_mode": "rule_v1",
                "seeded_skill_ids": sorted(seeded),
                "selected_skills": selected_ids,
                "seeded_skills": [skill_id for skill_id in selected_ids if skill_id in seeded],
                "selection_reasons": selection_reasons,
                "effective_skill_hits": effective_skill_hits,
                "ineffective_skill_hits": ineffective_skill_hits,
                "seed_sources": seed_sources,
            },
            started,
        )
