from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ExternalBenchmarkEvidence


class SwebenchEvidenceAdapter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.evidence_dir = output_dir / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def build_for_task(self, instance_id: str, result_payload: dict[str, Any]) -> ExternalBenchmarkEvidence:
        base = self.evidence_dir / instance_id
        base.mkdir(parents=True, exist_ok=True)

        operator_path = base / "operator_evidence.json"
        replay_path = base / "replay_evidence.json"
        patch_review_path = base / "patch_review_evidence.json"
        policy_path = base / "policy_evidence.json"
        prediction_path = base / "prediction_evidence.json"
        harness_path = base / "harness_evidence.json"

        operator_payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "instance_id": instance_id,
            "summary_available": True,
        }
        replay_payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "instance_id": instance_id,
            "trace_available": True,
        }
        patch_payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "instance_id": instance_id,
            "patch_generated": bool(result_payload.get("patch")),
        }
        policy_payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "instance_id": instance_id,
            "violations": result_payload.get("policy_violations") or [],
        }
        pred_payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "instance_id": instance_id,
            "prediction_path": result_payload.get("prediction_path", ""),
        }
        harness_payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "instance_id": instance_id,
            "harness_evaluated": bool(result_payload.get("harness_evaluated")),
            "harness_result_path": result_payload.get("harness_result_path", ""),
        }

        for p, pl in [
            (operator_path, operator_payload),
            (replay_path, replay_payload),
            (patch_review_path, patch_payload),
            (policy_path, policy_payload),
            (prediction_path, pred_payload),
            (harness_path, harness_payload),
        ]:
            p.write_text(json.dumps(pl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return ExternalBenchmarkEvidence(
            operator_evidence_path=str(operator_path),
            replay_evidence_path=str(replay_path),
            patch_review_path=str(patch_review_path),
            policy_evidence_path=str(policy_path),
            prediction_evidence_path=str(prediction_path),
            harness_evidence_path=str(harness_path),
        )

