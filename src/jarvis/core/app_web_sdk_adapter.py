"""Minimal App/Web SDK adapter for consuming UI bridge payloads.

Provides stable input models for App/Web clients consuming the
phase3_ui_bridge versioned payload envelope.

This is NOT a full frontend framework. It only defines:
  - BridgePayload: the raw envelope from run_phase3_ui_bridge.py
  - TaskSummaryModel: extracted task summary for UI display
  - ReviewFieldsModel: ordered review fields preserving insertion order
  - ReviewPaneModel: review pane with grouped sections
  - ReleaseGateModel: release gate summary for decision display
  - SdkInputModel: the unified model App/Web components should consume
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# ---- Constants ----
SUPPORTED_SCHEMA_ID = "jarvis.ui_bridge"
MIN_SCHEMA_VERSION = "1.0.0"
MIN_PAYLOAD_VERSION = "1.0.0"


class BridgeParseError(Exception):
    """Raised when a bridge payload fails schema/version validation."""


# ---- Models ----

class TaskSummaryModel:
    """Extracted task summary fields for UI components."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.task_id: str | None = raw.get("task_id")
        self.title: str | None = raw.get("title")
        self.status: str | None = raw.get("status")
        self.summary: str | None = raw.get("summary")
        self.counts: dict[str, int] = raw.get("counts") or {}
        self.timestamps: dict[str, str | None] = raw.get("timestamps") or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status,
            "summary": self.summary,
            "counts": self.counts,
            "timestamps": self.timestamps,
        }


class ReviewFieldItem:
    """Single ordered review field."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.path: str = raw.get("path", "")
        self.value: Any = raw.get("value")
        self.exists: bool = bool(raw.get("exists", False))

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "value": self.value, "exists": self.exists}


class ReviewFieldsModel:
    """Ordered review fields preserving insertion order for UI priority rendering."""

    def __init__(self, raw_fields: list[dict[str, Any]]) -> None:
        self.fields: list[ReviewFieldItem] = [ReviewFieldItem(f) for f in raw_fields]

    @property
    def paths(self) -> list[str]:
        return [f.path for f in self.fields]

    def to_dict(self) -> list[dict[str, Any]]:
        return [f.to_dict() for f in self.fields]


class ReviewPaneModel:
    """Review pane with grouped sections for UI rendering."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.task_summary: TaskSummaryModel | None = None
        if raw and raw.get("task_summary"):
            self.task_summary = TaskSummaryModel(raw["task_summary"])
        self.rules_warnings: list[dict] = list(raw.get("rules_warnings") or [])
        self.fallback_explanation: dict = raw.get("fallback_explanation") or {}
        self.checkpoint_compare_summary: dict = raw.get("checkpoint_compare_summary") or {}
        self.test_result_summary: dict = raw.get("test_result_summary") or {}
        self.finalize_summary: str | None = raw.get("finalize_summary")
        self.gate_status: dict = raw.get("gate_status") or {}
        self.ui_contract_version: str = raw.get("ui_contract_version", "")
        self.groups: dict = raw.get("groups") or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_summary": self.task_summary.to_dict() if self.task_summary else None,
            "rules_warnings": self.rules_warnings,
            "fallback_explanation": self.fallback_explanation,
            "checkpoint_compare_summary": self.checkpoint_compare_summary,
            "test_result_summary": self.test_result_summary,
            "finalize_summary": self.finalize_summary,
            "gate_status": self.gate_status,
            "ui_contract_version": self.ui_contract_version,
            "groups": self.groups,
        }


class ReleaseGateModel:
    """Release gate summary for decision / go-no-go display."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.available: bool = bool(raw.get("available", False))
        self.gate_name: str = raw.get("gate_name", "")
        self.passed: bool | None = raw.get("passed")
        self.headline: str | None = raw.get("headline")
        self.first_failure: str | None = raw.get("first_failure")
        self.acceptance: dict = raw.get("acceptance") or {}
        self.regression: dict = raw.get("regression") or {}
        self.run_at: str | None = raw.get("run_at")
        self.duration_ms: int | None = raw.get("duration_ms")

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "gate_name": self.gate_name,
            "passed": self.passed,
            "headline": self.headline,
            "first_failure": self.first_failure,
            "acceptance": self.acceptance,
            "regression": self.regression,
            "run_at": self.run_at,
            "duration_ms": self.duration_ms,
        }


class SdkInputModel:
    """Unified SDK input model -- the single object App/Web components should consume."""

    def __init__(
        self,
        *,
        task_summary: TaskSummaryModel | None = None,
        review_fields: ReviewFieldsModel | None = None,
        review_pane: ReviewPaneModel | None = None,
        release_gate: ReleaseGateModel | None = None,
        schema_version: str = "",
        payload_version: str = "",
        generated_at: str = "",
        source: str = "",
        request_id: str = "",
        correlation_id: str = "",
    ) -> None:
        self.task_summary = task_summary
        self.review_fields = review_fields
        self.review_pane = review_pane
        self.release_gate = release_gate
        self.schema_version = schema_version
        self.payload_version = payload_version
        self.generated_at = generated_at
        self.source = source
        self.request_id = request_id
        self.correlation_id = correlation_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_summary": self.task_summary.to_dict() if self.task_summary else None,
            "review_fields": self.review_fields.to_dict() if self.review_fields else [],
            "review_pane": self.review_pane.to_dict() if self.review_pane else None,
            "release_gate": self.release_gate.to_dict() if self.release_gate else None,
            "schema_version": self.schema_version,
            "payload_version": self.payload_version,
            "generated_at": self.generated_at,
            "source": self.source,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
        }


# ---- Adapter entry point ----

def parse_bridge_payload(payload: dict[str, Any]) -> SdkInputModel:
    """Parse a versioned bridge payload into a stable SDK input model.

    Raises BridgeParseError if schema/version validation fails.
    """
    schema_id = payload.get("schema_id", "")
    schema_version = payload.get("schema_version", "")
    payload_version = payload.get("payload_version", "")

    if schema_id != SUPPORTED_SCHEMA_ID:
        raise BridgeParseError(
            f"Unsupported schema_id: {schema_id!r} (expected {SUPPORTED_SCHEMA_ID!r})"
        )
    if schema_version != MIN_SCHEMA_VERSION:
        raise BridgeParseError(
            f"Unsupported schema_version: {schema_version!r} (minimum {MIN_SCHEMA_VERSION!r})"
        )
    if payload_version != MIN_PAYLOAD_VERSION:
        raise BridgeParseError(
            f"Unsupported payload_version: {payload_version!r} (minimum {MIN_PAYLOAD_VERSION!r})"
        )

    data = payload.get("data") or {}
    meta = payload.get("meta") or {}

    task_summary = TaskSummaryModel(data["task_summary"]) if data.get("task_summary") else None
    review_fields = ReviewFieldsModel(data.get("ordered_review_fields", []))
    review_pane = ReviewPaneModel(data.get("review_pane")) if data.get("review_pane") else None
    release_gate = ReleaseGateModel(data["release_gate_summary"]) if data.get("release_gate_summary") else None

    return SdkInputModel(
        task_summary=task_summary,
        review_fields=review_fields,
        review_pane=review_pane,
        release_gate=release_gate,
        schema_version=schema_version,
        payload_version=payload_version,
        generated_at=payload.get("generated_at", ""),
        source=meta.get("source", ""),
        request_id=meta.get("request_id", ""),
        correlation_id=meta.get("correlation_id", ""),
    )
