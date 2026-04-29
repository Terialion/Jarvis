"""Domain classifier / fast router for pre-runtime framing."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from ..result import error_result, ok_result
from .config import RoutingConfigManager
from .models import DomainRouteResult, VALID_DOMAINS


class DomainClassifier:
    def __init__(self, config_manager: RoutingConfigManager | None = None) -> None:
        self.config_manager = config_manager or RoutingConfigManager()

    def classify_domain(self, text: str, intent_hint: dict[str, Any] | None = None) -> dict:
        started = perf_counter()
        if not isinstance(text, str):
            return error_result(
                "ROUTING_INVALID_INPUT",
                "text must be a string",
                {"input_type": str(type(text))},
                started,
            )
        result = self.resolve_domain(text=text, intent_hint=intent_hint)
        return ok_result(result.to_dict(), started)

    def resolve_domain(self, text: str, intent_hint: dict[str, Any] | None = None) -> DomainRouteResult:
        lowered = (text or "").strip().lower()
        intent_hint = intent_hint or {}
        reasons: list[str] = []
        hits: dict[str, list[str]] = {domain: [] for domain in VALID_DOMAINS}

        hinted = str(intent_hint.get("domain") or "").strip().lower()
        if hinted in VALID_DOMAINS:
            reasons.append(f"intent_hint_domain:{hinted}")
            return DomainRouteResult(
                domain=hinted,
                confidence=0.92,
                reasons=reasons,
                extracted_signals={"intent_hint_domain": hinted},
                fallback_used=False,
            )

        domain_rules = self.config_manager.config.get("domain_rules") or {}
        for domain, tokens in domain_rules.items():
            for token in tokens:
                if token in lowered:
                    hits[domain].append(token)

        ranked = sorted(
            [(domain, len(tokens), tokens) for domain, tokens in hits.items() if tokens],
            key=lambda item: (-item[1], item[0]),
        )
        if not ranked:
            return self.fallback_domain(text, reason="no_domain_rule_hit")

        winner, count, tokens = ranked[0]
        reasons.append(f"rule_match:{winner}")
        reasons.extend([f"token:{token}" for token in tokens[:3]])
        confidence = min(0.95, 0.55 + 0.12 * count)
        return DomainRouteResult(
            domain=winner,
            confidence=confidence,
            reasons=reasons,
            extracted_signals={"token_hits": {winner: tokens}, "ranked_hits": ranked[:3]},
            fallback_used=False,
        )

    def fallback_domain(self, text: str, reason: str = "domain_fallback") -> DomainRouteResult:
        _ = text
        fallback_domain = str((self.config_manager.config.get("fallbacks") or {}).get("domain") or "think")
        if fallback_domain not in VALID_DOMAINS:
            fallback_domain = "think"
        return DomainRouteResult(
            domain=fallback_domain,
            confidence=0.45,
            reasons=[reason],
            extracted_signals={"fallback_reason": reason},
            fallback_used=True,
        )

    def explain_domain_choice(self, result: dict[str, Any]) -> dict:
        started = perf_counter()
        if not isinstance(result, dict):
            return error_result(
                "ROUTING_INVALID_INPUT",
                "result must be a dict",
                {"input_type": str(type(result))},
                started,
            )
        domain = result.get("domain")
        if domain not in VALID_DOMAINS:
            return error_result(
                "ROUTING_INVALID_INPUT",
                f"invalid domain: {domain}",
                {"domain": domain, "valid_domains": list(VALID_DOMAINS)},
                started,
            )
        reasons = list(result.get("reasons") or [])
        confidence = float(result.get("confidence") or 0.0)
        summary = f"domain={domain} confidence={round(confidence, 3)} reasons={';'.join(reasons[:3])}"
        return ok_result({"summary": summary, "result": result}, started)
