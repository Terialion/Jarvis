"""Policy + default skill selector (pre-runtime, non-executing)."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from ..result import error_result, ok_result
from .config import RoutingConfigManager
from .models import PolicySelectionResult


class PolicySkillSelector:
    def __init__(self, config_manager: RoutingConfigManager | None = None) -> None:
        self.config_manager = config_manager or RoutingConfigManager()

    def select_policies(self, domain: str, intent: str, task_shape: str, entities: dict[str, Any] | None = None) -> dict:
        started = perf_counter()
        if not isinstance(domain, str) or not isinstance(intent, str):
            return error_result(
                "ROUTING_INVALID_INPUT",
                "domain and intent must be strings",
                {"domain_type": str(type(domain)), "intent_type": str(type(intent))},
                started,
            )
        result = self._resolve(domain=domain, intent=intent, task_shape=task_shape, entities=entities or {})
        return ok_result(result.to_dict(), started)

    def select_default_skills(self, domain: str, intent: str, task_shape: str) -> list[str]:
        skills: list[str] = []
        d = domain.lower()
        i = intent.lower()
        configured = self.config_manager.config.get("default_skills") or {}
        domain_skills = list(configured.get(d) or [])
        skills.extend([str(item) for item in domain_skills])
        if i.startswith("code.") and "skill.repo_fix" not in skills:
            skills.extend(["skill.repo_fix"])
        if task_shape in {"multi_step", "cross_domain"}:
            skills.append("skill.command_verify")
        return self._uniq(skills)

    def merge_policy_hints(self, policy_result: PolicySelectionResult) -> dict[str, Any]:
        planner_hints = dict(policy_result.planner_hints)
        planner_hints.setdefault("policy_count", len(policy_result.selected_policies))
        planner_hints.setdefault("default_skill_count", len(policy_result.attached_default_skills))
        return {
            "planner_hints": planner_hints,
            "approval_risk_hints": dict(policy_result.approval_risk_hints),
            "selected_policies": list(policy_result.selected_policies),
            "attached_default_skills": list(policy_result.attached_default_skills),
        }

    def explain_policy_choice(self, result: dict[str, Any]) -> dict:
        started = perf_counter()
        if not isinstance(result, dict):
            return error_result(
                "ROUTING_INVALID_INPUT",
                "result must be dict",
                {"input_type": str(type(result))},
                started,
            )
        selected = list(result.get("selected_policies") or [])
        skills = list(result.get("attached_default_skills") or [])
        return ok_result(
            {
                "summary": f"policies={len(selected)} skills={len(skills)}",
                "selection_reasons": list(result.get("selection_reasons") or []),
            },
            started,
        )

    def _resolve(self, *, domain: str, intent: str, task_shape: str, entities: dict[str, Any]) -> PolicySelectionResult:
        selected: list[str] = []
        rejected: list[dict[str, Any]] = []
        reasons: list[str] = []
        approval_hints: dict[str, Any] = {"approval_required": False, "risk_level": "low", "reasons": []}
        planner_hints: dict[str, Any] = {
            "task_shape": task_shape,
            "likely_multi_step": task_shape == "multi_step",
            "source_preference": "local_tools",
            "skill_preferences": [],
        }
        d = domain.lower()
        i = intent.lower()
        policy_rules = self.config_manager.config.get("policy_rules") or {}
        domain_map = policy_rules.get("domain") or {}
        intent_map = policy_rules.get("intent_contains") or {}
        source_pref = self.config_manager.config.get("source_preferences") or {}

        if d in domain_map:
            selected.extend([str(item) for item in list(domain_map.get(d) or [])])
            reasons.append(f"domain_policy:{d}")
            if d == "act" and i.startswith("ops."):
                approval_hints = {
                    "approval_required": True,
                    "risk_level": "medium",
                    "reasons": ["domain_act_requires_guard"],
                }
            if "retrieval" in i:
                intent_policies = list(intent_map.get("retrieval") or [])
                selected.extend([str(item) for item in intent_policies])
                planner_hints["skill_preferences"].append("skill.command_verify")
        elif d == "act":
            approval_hints = {
                "approval_required": True,
                "risk_level": "medium",
                "reasons": ["domain_act_requires_guard"],
            }
        if d == "think":
            planner_hints["skill_preferences"].append("skill.repo_fix")
        if d not in domain_map and d not in {"act", "think"}:
            rejected.append({"policy": "domain_specific_policy", "reason": "no_specific_mapping"})
        for intent_key, mapped in intent_map.items():
            if intent_key and intent_key in i:
                selected.extend([str(item) for item in list(mapped or [])])
                reasons.append(f"intent_policy:{intent_key}")

        if task_shape == "multi_step":
            selected.append("plan-before-act")
            planner_hints["likely_multi_step"] = True
            planner_hints["decomposition_required"] = True
        planner_hints["source_preference"] = str(source_pref.get(d) or planner_hints["source_preference"])
        if entities.get("command_hint"):
            approval_hints["approval_required"] = True
            approval_hints["risk_level"] = "medium"
            approval_hints["reasons"] = list(approval_hints.get("reasons") or []) + ["command_hint_detected"]
        if entities.get("file_hint") and d in {"act", "create"}:
            approval_hints["approval_required"] = True
            approval_hints["risk_level"] = "high" if "deploy" in i else "medium"
            approval_hints["reasons"] = list(approval_hints.get("reasons") or []) + ["file_write_likely"]

        skills = self.select_default_skills(domain=domain, intent=intent, task_shape=task_shape)
        if planner_hints.get("skill_preferences"):
            skills = self._uniq(list(planner_hints["skill_preferences"]) + skills)

        fallback_used = not selected and not skills
        if fallback_used:
            selected = ["safe-default-policy"]
            reasons.append("policy_fallback")
        return PolicySelectionResult(
            selected_policies=self._uniq(selected),
            attached_default_skills=skills,
            rejected_policies=rejected,
            selection_reasons=reasons,
            approval_risk_hints=approval_hints,
            planner_hints=planner_hints,
            fallback_used=fallback_used,
        )

    @staticmethod
    def _uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                output.append(item)
        return output
