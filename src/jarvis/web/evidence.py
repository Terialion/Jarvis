from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .schema import ReadableDocument


@dataclass
class EvidenceObject:
    evidence_id: str
    source_url: str
    source_title: str
    source_type: str
    quote: str
    summary: str
    stance: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceCoverage:
    source_coverage_score: float
    has_official_source: bool
    has_github_source: bool
    evidence_count: int
    weaknesses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_evidence(documents: list[ReadableDocument], *, max_per_document: int = 3) -> list[EvidenceObject]:
    evidence: list[EvidenceObject] = []
    for doc_index, document in enumerate(documents, start=1):
        parts = [part.strip() for part in str(document.text or "").split(".") if part.strip()]
        if not parts:
            parts = [str(document.text or "").strip()]
        for part_index, part in enumerate(parts[: max_per_document], start=1):
            lowered = part.lower()
            stance = "context"
            if any(word in lowered for word in ("confirmed", "notes", "workaround", "limitation")):
                stance = "supports"
            if "not" in lowered and "supported" in lowered:
                stance = "contradicts"
            evidence.append(
                EvidenceObject(
                    evidence_id=f"ev_{doc_index}_{part_index}",
                    source_url=document.final_url,
                    source_title=document.title,
                    source_type=document.source_type,
                    quote=part[:220],
                    summary=part[:220],
                    stance=stance,
                    confidence=0.8 if document.source_type in {"official_docs", "github_issue", "github_pr"} else 0.5,
                )
            )
    return evidence


def judge_source_coverage(evidence: list[EvidenceObject], intent_type: str) -> SourceCoverage:
    has_official = any(item.source_type == "official_docs" for item in evidence)
    has_github = any(item.source_type in {"github_issue", "github_pr"} for item in evidence)
    kinds = {item.source_type for item in evidence}
    weaknesses: list[str] = []
    score = 0.0
    if intent_type == "bug_verification":
        if has_official:
            score += 0.5
        else:
            weaknesses.append("missing_official_source")
        if has_github:
            score += 0.4
        else:
            weaknesses.append("missing_github_source")
    elif intent_type == "docs_lookup":
        if has_official:
            score += 0.8
        else:
            weaknesses.append("missing_official_source")
    else:
        if len(kinds) >= 2:
            score += 0.7
        else:
            weaknesses.append("limited_source_diversity")
    if evidence:
        score += 0.1
    return SourceCoverage(
        source_coverage_score=min(score, 1.0),
        has_official_source=has_official,
        has_github_source=has_github,
        evidence_count=len(evidence),
        weaknesses=weaknesses,
    )

