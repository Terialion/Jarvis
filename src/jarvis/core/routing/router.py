"""Intent/Policy routing bundle orchestrator."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from ..result import error_result, ok_result
from .config import RoutingConfigManager
from .domain_classifier import DomainClassifier
from .intent_router import IntentRouter
from .models import RouteResultBundle
from .policy_selector import PolicySkillSelector


class IntentPolicyRouter:
    """Pre-runtime routing layer: domain -> intent -> policy/skills."""

    def __init__(
        self,
        *,
        config_manager: RoutingConfigManager | None = None,
        domain_classifier: DomainClassifier | None = None,
        intent_router: IntentRouter | None = None,
        policy_selector: PolicySkillSelector | None = None,
    ) -> None:
        self.config_manager = config_manager or RoutingConfigManager()
        self.domain_classifier = domain_classifier or DomainClassifier(self.config_manager)
        self.intent_router = intent_router or IntentRouter(self.config_manager)
        self.policy_selector = policy_selector or PolicySkillSelector(self.config_manager)

    def route(self, text: str, intent_hint: dict[str, Any] | None = None) -> dict:
        started = perf_counter()
        if not isinstance(text, str):
            return error_result(
                "ROUTING_INVALID_INPUT",
                "text must be string",
                {"input_type": str(type(text))},
                started,
            )
        try:
            domain_obj = self.domain_classifier.resolve_domain(text=text, intent_hint=intent_hint)
            intent_obj = self.intent_router.resolve_intent(text=text, domain=domain_obj.domain)
            policy_obj = self.policy_selector._resolve(
                domain=domain_obj.domain,
                intent=intent_obj.intent,
                task_shape=intent_obj.task_shape,
                entities=intent_obj.extracted_entities,
            )
            confidence = round((domain_obj.confidence + intent_obj.confidence) / 2.0, 4)
            reasons = list(domain_obj.reasons) + list(intent_obj.reasons) + list(policy_obj.selection_reasons)
            fallback_used = bool(domain_obj.fallback_used or intent_obj.fallback_used or policy_obj.fallback_used)
            fallback_codes: list[str] = []
            if domain_obj.fallback_used:
                fallback_codes.append("ROUTING_DOMAIN_FALLBACK")
            if intent_obj.fallback_used:
                fallback_codes.append("ROUTING_INTENT_FALLBACK")
            if policy_obj.fallback_used:
                fallback_codes.append("ROUTING_POLICY_FALLBACK")
            trace_metadata = {
                "route_source": intent_obj.route_source,
                "domain_fallback_used": domain_obj.fallback_used,
                "intent_fallback_used": intent_obj.fallback_used,
                "policy_fallback_used": policy_obj.fallback_used,
                "fallback_codes": fallback_codes,
                "routing_config_source": self.config_manager.source,
                "routing_config_version": self.config_manager.config.get("version"),
            }
            low_conf_threshold = float((self.config_manager.config.get("fallbacks") or {}).get("low_confidence_threshold") or 0.5)
            low_confidence = confidence < low_conf_threshold
            if low_confidence:
                reasons.append("low_confidence_route")
                trace_metadata["low_confidence_handling"] = {
                    "threshold": low_conf_threshold,
                    "strategy": "fallback_to_summary",
                }
            bundle = RouteResultBundle(
                domain=domain_obj.domain,
                intent=intent_obj.intent,
                confidence=confidence,
                reasons=reasons,
                extracted_entities=intent_obj.extracted_entities,
                attached_default_skills=policy_obj.attached_default_skills,
                selected_policies=policy_obj.selected_policies,
                planner_hints=policy_obj.planner_hints,
                approval_risk_hints=policy_obj.approval_risk_hints,
                trace_metadata=trace_metadata,
                fallback_used=fallback_used,
            )
            return ok_result(
                {
                    "domain_result": domain_obj.to_dict(),
                    "intent_result": intent_obj.to_dict(),
                    "policy_result": policy_obj.to_dict(),
                    "route_result": bundle.to_dict(),
                },
                started,
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return error_result(
                "ROUTING_INTERNAL_ERROR",
                "routing pipeline failed",
                {"exception": str(exc)},
                started,
            )

    def reload_routing_config(self, path: str | None = None) -> dict:
        return self.config_manager.reload(path)

    def validate_routing_config(self, path: str) -> dict:
        return self.config_manager.validate_file(path)

    def route_snapshot_tests(self, samples: list[dict[str, Any]]) -> dict:
        return self.config_manager.run_drift_snapshot(samples, self.route)
