"""Gap-closure ledger parsing, scoring, and comparable-gate evaluation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

CAPABILITY_GROUPS = [
    "core_local_execution",
    "gateway_channels_nodes",
    "skill_harness_ecosystem",
    "approval_sandbox_policy",
    "hooks_settings_mcp",
    "subagents_planning_modes",
    "memory_profiles_learning_loop",
    "operator_quality_surface",
    "product_onboarding_demo",
    "benchmark_regression",
    "minimal_agent_loop_clarity",
    "rethink_replan_recovery",
]

COMPARABLE_GATE_THRESHOLDS = {
    "functional_coverage_min": 70.0,
    "safety_approval_rollback_min": 80.0,
    "core_e2e_pass_rate_min": 90.0,
}

GAP_LEVEL_WEIGHTS = {
    "none": 0,
    "minor": 1,
    "medium": 2,
    "major": 3,
    "critical": 4,
}

_BASE_SCORE_BY_LEVEL = {
    "none": 100.0,
    "minor": 75.0,
    "medium": 50.0,
    "major": 25.0,
    "critical": 0.0,
}


def _evidence_maturity_bonus(entry: "GapEntry", repo_root: Path) -> float:
    """Score bonus that rewards non-ledger-only completion evidence.

    This prevents raw gap_level editing from being enough to hit high scores.
    """
    bonus = 0.0
    if entry.implementation_status == "done":
        bonus += 8.0
    if len(entry.tests) >= 3:
        bonus += 5.0
    if len(entry.evidence) >= 4:
        bonus += 5.0
    if str(entry.owner_module).strip():
        owner_path = repo_root / str(entry.owner_module)
        if owner_path.exists():
            bonus += 4.0
    if any("tests/" in t.replace("\\", "/") for t in entry.tests):
        bonus += 3.0
    if any("operator" in e.lower() or "replay" in e.lower() for e in entry.evidence):
        bonus += 5.0
    return bonus


def _has_artifact_backed_evidence(entry: "GapEntry", repo_root: Path) -> bool:
    for e in (entry.evidence or []):
        text = str(e).strip()
        if text.startswith("artifact:"):
            rel = text.split("artifact:", 1)[1].strip()
            if rel and (repo_root / rel).exists():
                return True
    return False


def _evidence_confidence(entry: "GapEntry", repo_root: Path) -> str:
    ev = [str(x).lower() for x in (entry.evidence or [])]
    has_dynamic = any("dynamic" in e or "sample" in e or "random_replay_audit" in e for e in ev) and _has_artifact_backed_evidence(entry, repo_root)
    has_operator = any("operator" in e or "/operator/" in e for e in ev)
    has_runtime = any("runtime" in e or "replay" in e for e in ev)
    if has_dynamic and has_operator and has_runtime:
        return "high"
    if (has_operator and has_runtime) or has_dynamic:
        return "medium"
    return "low"


def _score_cap_from_confidence(conf: str, base_level: str) -> float:
    if conf == "high":
        return 100.0 if base_level == "none" else 95.0
    if conf == "medium":
        return 90.0
    return 85.0


@dataclass
class GapEntry:
    capability_id: str
    capability_group: str
    reference_system: str
    reference_capability: str
    jarvis_current_status: str
    gap_level: str
    target_acceptance: list[str]
    implementation_status: str
    tests: list[str]
    owner_module: str
    stop_condition: str
    evidence: list[str]
    reuse_classification: str
    reuse_reason: str
    replacement_path: str
    next_sprint_plan: str | None = None


@dataclass
class GateEvaluation:
    passed: bool
    functional_coverage: float
    safety_approval_rollback: float
    core_e2e_pass_rate: float
    critical_gap_count: int
    major_gap_count: int
    blockers: list[str]
    major_gap_requires_plan: bool


class GapClosureEngine:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.ledger_path = self.repo_root / "docs" / "benchmarks" / "gap_ledger.json"
        self.ledger_schema_path = self.repo_root / "docs" / "schemas" / "benchmarks" / "gap_ledger.schema.json"

    def load_ledger(self) -> dict[str, Any]:
        payload = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        self._validate_ledger_schema(payload)
        return payload

    def parse_entries(self, ledger: dict[str, Any]) -> list[GapEntry]:
        entries: list[GapEntry] = []
        for raw in ledger.get("entries", []):
            entries.append(GapEntry(**raw))
        return entries

    def select_top_gaps(self, entries: list[GapEntry], *, limit: int = 10) -> list[GapEntry]:
        ranked = sorted(
            entries,
            key=lambda e: (
                GAP_LEVEL_WEIGHTS.get(e.gap_level, -1),
                1 if e.implementation_status != "done" else 0,
            ),
            reverse=True,
        )
        return ranked[:limit]

    def compute_scores(self, entries: list[GapEntry], core_e2e_pass_rate: float) -> dict[str, Any]:
        if not entries:
            return {
                "functional_coverage": 0.0,
                "safety_approval_rollback": 0.0,
                "core_e2e_pass_rate": core_e2e_pass_rate,
                "critical_gap_count": 0,
                "major_gap_count": 0,
                "group_scores": {},
            }
        group_scores: dict[str, list[float]] = {g: [] for g in CAPABILITY_GROUPS}
        critical_gap_count = 0
        major_gap_count = 0
        safety_entries = 0
        safety_points = 0.0
        functional_points = 0.0
        for entry in entries:
            level = GAP_LEVEL_WEIGHTS.get(entry.gap_level, 4)
            base = _BASE_SCORE_BY_LEVEL.get(entry.gap_level, 0.0)
            conf = _evidence_confidence(entry, self.repo_root)
            score = min(_score_cap_from_confidence(conf, entry.gap_level), base + _evidence_maturity_bonus(entry, self.repo_root))
            functional_points += score
            group_scores.setdefault(entry.capability_group, []).append(score)
            if level >= GAP_LEVEL_WEIGHTS["critical"]:
                critical_gap_count += 1
            if level >= GAP_LEVEL_WEIGHTS["major"]:
                major_gap_count += 1
            if entry.capability_group in {"approval_sandbox_policy", "core_local_execution"}:
                safety_entries += 1
                safety_points += score
        functional_coverage = round(functional_points / len(entries), 2)
        safety_approval_rollback = round(
            (safety_points / safety_entries) if safety_entries else functional_coverage,
            2,
        )
        normalized_group_scores = {
            group: round(sum(values) / len(values), 2) if values else None
            for group, values in group_scores.items()
        }
        return {
            "functional_coverage": functional_coverage,
            "safety_approval_rollback": safety_approval_rollback,
            "core_e2e_pass_rate": round(core_e2e_pass_rate, 2),
            "critical_gap_count": critical_gap_count,
            "major_gap_count": major_gap_count,
            "group_scores": normalized_group_scores,
        }

    def evaluate_gate(self, scores: dict[str, Any], entries: list[GapEntry]) -> GateEvaluation:
        blockers: list[str] = []
        functional = float(scores["functional_coverage"])
        safety = float(scores["safety_approval_rollback"])
        e2e = float(scores["core_e2e_pass_rate"])
        critical = int(scores["critical_gap_count"])
        major = int(scores["major_gap_count"])
        if functional < COMPARABLE_GATE_THRESHOLDS["functional_coverage_min"]:
            blockers.append("functional_coverage_below_threshold")
        if safety < COMPARABLE_GATE_THRESHOLDS["safety_approval_rollback_min"]:
            blockers.append("safety_approval_rollback_below_threshold")
        if e2e < COMPARABLE_GATE_THRESHOLDS["core_e2e_pass_rate_min"]:
            blockers.append("core_e2e_pass_rate_below_threshold")
        if critical > 0:
            blockers.append("critical_gap_exists")
        major_missing_plan = any(
            e.gap_level == "major" and not (e.next_sprint_plan or "").strip() for e in entries
        )
        if major_missing_plan:
            blockers.append("major_gap_missing_next_sprint_plan")
        return GateEvaluation(
            passed=not blockers,
            functional_coverage=functional,
            safety_approval_rollback=safety,
            core_e2e_pass_rate=e2e,
            critical_gap_count=critical,
            major_gap_count=major,
            blockers=blockers,
            major_gap_requires_plan=major_missing_plan,
        )

    def build_round_report(
        self,
        *,
        round_index: int,
        goal: str,
        scope: str,
        scores: dict[str, Any],
        gate: GateEvaluation,
        top_gaps: list[GapEntry],
        test_summary: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "round": round_index,
            "goal": goal,
            "scope": scope,
            "comparable_gate": asdict(gate),
            "scores": scores,
            "top_gaps": [asdict(g) for g in top_gaps],
            "test_summary": test_summary,
            "required_sections": [
                "Goal",
                "Scope",
                "Reference Comparison Summary",
                "Gap Ledger Update",
                "Legacy / Reference Reuse Decision",
                "Files Changed",
                "Interfaces Implemented",
                "Runtime / Skill / Operator / Replay Integration",
                "Policies / Schemas / Eval Added",
                "Tests Added",
                "Benchmark Result",
                "Comparable Gate Status",
                "Progress Update",
                "File & Directory Structure Update",
                "Module → File Mapping",
                "Validation Result",
                "Remaining Risks",
                "Next Recommended Step",
            ],
        }

    def _validate_ledger_schema(self, payload: dict[str, Any]) -> None:
        schema = json.loads(self.ledger_schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
        if errors:
            details = "; ".join(f"{'/'.join(map(str, err.path))}: {err.message}" for err in errors[:5])
            raise ValueError(f"gap_ledger schema validation failed: {details}")
