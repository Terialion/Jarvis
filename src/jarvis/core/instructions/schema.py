from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InstructionSource:
    scope: str
    path: str
    loaded: bool
    bytes: int = 0
    skipped_reason: str | None = None


@dataclass
class InstructionBundle:
    sources: list[InstructionSource] = field(default_factory=list)
    combined_text: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sources": [source.__dict__ for source in self.sources],
            "combined_text": self.combined_text,
            "warnings": list(self.warnings),
        }

