"""Intent routing layer (separate from domain classifier)."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from ..result import error_result, ok_result
from .config import RoutingConfigManager
from .models import IntentRouteResult, VALID_TASK_SHAPES


class IntentRouter:
    def __init__(self, config_manager: RoutingConfigManager | None = None) -> None:
        self.config_manager = config_manager or RoutingConfigManager()

    def classify_intent(self, text: str, domain: str) -> dict:
        started = perf_counter()
        if not isinstance(text, str) or not isinstance(domain, str):
            return error_result(
                "ROUTING_INVALID_INPUT",
                "text/domain must be string",
                {"text_type": str(type(text)), "domain_type": str(type(domain))},
                started,
            )
        result = self.resolve_intent(text=text, domain=domain)
        return ok_result(result.to_dict(), started)

    def resolve_intent(self, text: str, domain: str) -> IntentRouteResult:
        lowered = (text or "").strip().lower()
        reasons: list[str] = []
        hits: list[tuple[str, int, list[str]]] = []
        intent_rules = self.config_manager.config.get("intent_rules") or {}
        for intent, tokens in intent_rules.items():
            matched = [token for token in tokens if token in lowered]
            if matched:
                hits.append((intent, len(matched), matched))

        extracted_entities = self.extract_entities(text=text, domain=domain)
        task_shape = self.infer_task_shape(text=text, domain=domain, entities=extracted_entities)
        if not hits:
            fallback_intent = str((self.config_manager.config.get("fallbacks") or {}).get("intent") or self._domain_default_intent(domain))
            return IntentRouteResult(
                intent=fallback_intent,
                confidence=0.42,
                reasons=[f"intent_fallback:{domain}"],
                extracted_entities=extracted_entities,
                task_shape=task_shape,
                route_source="fallback",
                fallback_used=True,
            )

        hits.sort(key=lambda item: (-item[1], item[0]))
        winner, count, matched = hits[0]
        reasons.append(f"rule_match:{winner}")
        reasons.extend([f"token:{token}" for token in matched[:3]])
        confidence = min(0.93, 0.52 + count * 0.13)
        return IntentRouteResult(
            intent=winner,
            confidence=confidence,
            reasons=reasons,
            extracted_entities=extracted_entities,
            task_shape=task_shape,
            route_source="rules",
            fallback_used=False,
        )

    def extract_entities(self, text: str, domain: str) -> dict[str, Any]:
        lowered = (text or "").lower()
        entities: dict[str, Any] = {
            "domain": domain,
            "file_hint": None,
            "symbol_hint": None,
            "command_hint": None,
        }
        if ".py" in lowered:
            words = [w.strip(" ,;:()[]{}") for w in lowered.split()]
            entities["file_hint"] = next((w for w in words if w.endswith(".py")), None)
        if "def " in lowered:
            suffix = lowered.split("def ", 1)[1]
            entities["symbol_hint"] = suffix.split("(", 1)[0].strip() or None
        if "pytest" in lowered or "python -m pytest" in lowered:
            entities["command_hint"] = "pytest"
        elif "python " in lowered and "-c" in lowered:
            entities["command_hint"] = "python -c"
        return entities

    def infer_task_shape(self, text: str, domain: str, entities: dict[str, Any] | None = None) -> str:
        lowered = (text or "").lower()
        entities = entities or {}
        if any(marker in lowered for marker in ("then", "after that", "之后", "然后", "并且")):
            return "multi_step"
        if domain in {"act", "think"} and ("test" in lowered or entities.get("file_hint")):
            return "multi_step"
        if any(marker in lowered for marker in ("and", "cross", "across", "同时")) and domain in {"inform", "think"}:
            return "cross_domain"
        return "single_step"

    def explain_intent_choice(self, result: dict[str, Any]) -> dict:
        started = perf_counter()
        if not isinstance(result, dict):
            return error_result(
                "ROUTING_INVALID_INPUT",
                "result must be dict",
                {"input_type": str(type(result))},
                started,
            )
        shape = str(result.get("task_shape") or "")
        if shape not in VALID_TASK_SHAPES:
            return error_result(
                "ROUTING_INVALID_INPUT",
                f"invalid task_shape: {shape}",
                {"task_shape": shape, "valid_task_shapes": list(VALID_TASK_SHAPES)},
                started,
            )
        intent = result.get("intent")
        confidence = float(result.get("confidence") or 0.0)
        reasons = list(result.get("reasons") or [])
        return ok_result(
            {
                "summary": f"intent={intent} shape={shape} confidence={round(confidence, 3)}",
                "reasons": reasons,
            },
            started,
        )

    @staticmethod
    def _domain_default_intent(domain: str) -> str:
        defaults = {
            "inform": "retrieval.read",
            "act": "ops.command",
            "think": "analysis.plan",
            "recall": "memory.recall",
            "create": "code.fix",
            "monitor": "ops.command",
        }
        return defaults.get(str(domain or "").lower(), "analysis.plan")
