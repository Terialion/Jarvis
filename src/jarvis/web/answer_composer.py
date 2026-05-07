from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .evidence import EvidenceObject, SourceCoverage


@dataclass
class ComposedAnswer:
    final_answer: str
    output_type: str
    confidence: float
    remaining_questions: list[str] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnswerComposer:
    def compose(self, *, user_input: str, evidence: list[EvidenceObject], coverage: SourceCoverage) -> ComposedAnswer:
        grouped: dict[str, list[EvidenceObject]] = {}
        for item in evidence:
            grouped.setdefault(item.source_type, []).append(item)
        official = grouped.get("official_docs", [])
        github = grouped.get("github_issue", []) + grouped.get("github_pr", [])
        other = [item for item in evidence if item.source_type not in {"official_docs", "github_issue", "github_pr"}]
        confidence = round(coverage.source_coverage_score, 2)
        output_type = "answer" if confidence >= 0.6 else "partial"
        lines = ["结论："]
        if evidence:
            lines.append(f"- 基于已检索到的来源，当前问题的结论置信度约为 {confidence:.2f}。")
        else:
            lines.append("- 暂未找到足够证据，无法给出可靠结论。")
        lines.append("证据：")
        lines.append("- 官方来源：" + ("; ".join(f"{item.source_title} ({item.source_url})" for item in official[:2]) if official else " none"))
        lines.append("- GitHub 来源：" + ("; ".join(f"{item.source_title} ({item.source_url})" for item in github[:2]) if github else " none"))
        lines.append("- 其他来源：" + ("; ".join(f"{item.source_title} ({item.source_url})" for item in other[:2]) if other else " none"))
        lines.append("不确定性：")
        if coverage.weaknesses:
            lines.append("- " + ", ".join(coverage.weaknesses))
        else:
            lines.append("- 当前来源覆盖较完整，但仍应关注后续发布说明。")
        lines.append("后续建议：")
        lines.append("- 如需更高把握，可继续查看 release notes 或相关 PR。")
        refs = [
            {"url": item.source_url, "title": item.source_title, "source_type": item.source_type, "stance": item.stance}
            for item in evidence[:6]
        ]
        remaining = list(coverage.weaknesses)
        return ComposedAnswer(final_answer="\n".join(lines), output_type=output_type, confidence=confidence, remaining_questions=remaining, source_refs=refs)


class AnswerComposer:
    def compose(self, *, user_input: str, evidence: list[EvidenceObject], coverage: SourceCoverage) -> ComposedAnswer:
        _ = user_input
        grouped: dict[str, list[EvidenceObject]] = {}
        for item in evidence:
            grouped.setdefault(item.source_type, []).append(item)
        official = grouped.get("official_docs", [])
        github = grouped.get("github_issue", []) + grouped.get("github_pr", [])
        other = [item for item in evidence if item.source_type not in {"official_docs", "github_issue", "github_pr"}]
        confidence = round(coverage.source_coverage_score, 2)
        output_type = "answer" if confidence >= 0.6 and evidence else "partial"
        lines = ["结论："]
        if evidence:
            lines.append(f"- 当前基于已检索证据的结论可信度约为 {confidence:.2f}。")
        else:
            lines.append("- 暂未找到足够证据，无法给出可靠结论。")
        lines.append("证据：")
        lines.append("- 官方来源：" + ("; ".join(f"{item.source_title} ({item.source_url})" for item in official[:2]) if official else " none"))
        lines.append("- GitHub 来源：" + ("; ".join(f"{item.source_title} ({item.source_url})" for item in github[:2]) if github else " none"))
        lines.append("- 其他来源：" + ("; ".join(f"{item.source_title} ({item.source_url})" for item in other[:2]) if other else " none"))
        lines.append("不确定性：")
        if coverage.weaknesses:
            lines.append("- " + ", ".join(coverage.weaknesses))
        else:
            lines.append("- 当前来源覆盖较完整，但仍建议关注后续更新。")
        lines.append("后续建议：")
        lines.append("- 如需更高把握，可继续核对 release notes、PR 或后续官方说明。")
        refs = [
            {"url": item.source_url, "title": item.source_title, "source_type": item.source_type, "stance": item.stance}
            for item in evidence[:6]
        ]
        return ComposedAnswer(
            final_answer="\n".join(lines),
            output_type=output_type,
            confidence=confidence,
            remaining_questions=list(coverage.weaknesses),
            source_refs=refs,
        )
