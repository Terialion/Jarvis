"""Structured models for Intent/Policy pre-routing layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_DOMAINS = ("inform", "act", "think", "recall", "create", "monitor")
VALID_TASK_SHAPES = ("single_step", "multi_step", "cross_domain")


@dataclass
class DomainRouteResult:
    domain: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    extracted_signals: dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "confidence": round(float(self.confidence), 4),
            "reasons": list(self.reasons),
            "extracted_signals": dict(self.extracted_signals),
            "fallback_used": bool(self.fallback_used),
        }


@dataclass
class IntentRouteResult:
    intent: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    extracted_entities: dict[str, Any] = field(default_factory=dict)
    task_shape: str = "single_step"
    route_source: str = "rules"
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": round(float(self.confidence), 4),
            "reasons": list(self.reasons),
            "extracted_entities": dict(self.extracted_entities),
            "task_shape": self.task_shape,
            "route_source": self.route_source,
            "fallback_used": bool(self.fallback_used),
        }


@dataclass
class PolicySelectionResult:
    selected_policies: list[str] = field(default_factory=list)
    attached_default_skills: list[str] = field(default_factory=list)
    rejected_policies: list[dict[str, Any]] = field(default_factory=list)
    selection_reasons: list[str] = field(default_factory=list)
    approval_risk_hints: dict[str, Any] = field(default_factory=dict)
    planner_hints: dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_policies": list(self.selected_policies),
            "attached_default_skills": list(self.attached_default_skills),
            "rejected_policies": list(self.rejected_policies),
            "selection_reasons": list(self.selection_reasons),
            "approval_risk_hints": dict(self.approval_risk_hints),
            "planner_hints": dict(self.planner_hints),
            "fallback_used": bool(self.fallback_used),
        }


@dataclass
class RouteResultBundle:
    domain: str
    intent: str
    confidence: float
    reasons: list[str]
    extracted_entities: dict[str, Any]
    attached_default_skills: list[str]
    selected_policies: list[str]
    planner_hints: dict[str, Any]
    approval_risk_hints: dict[str, Any]
    trace_metadata: dict[str, Any]
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "intent": self.intent,
            "confidence": round(float(self.confidence), 4),
            "reasons": list(self.reasons),
            "extracted_entities": dict(self.extracted_entities),
            "attached_default_skills": list(self.attached_default_skills),
            "selected_policies": list(self.selected_policies),
            "planner_hints": dict(self.planner_hints),
            "approval_risk_hints": dict(self.approval_risk_hints),
            "trace_metadata": dict(self.trace_metadata),
            "fallback_used": bool(self.fallback_used),
        }
