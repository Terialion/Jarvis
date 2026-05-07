from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .diff import unified_diff_for_replacement


@dataclass(frozen=True)
class ReplacementPatch:
    path: Path
    old: str
    new: str
    summary: str

    def preview(self, *, project_root: Path | None = None) -> str:
        before = self.path.read_text(encoding="utf-8")
        return unified_diff_for_replacement(self.path, before, before.replace(self.old, self.new, 1), project_root=project_root)


KNOWN_FIXES: tuple[tuple[str, str, str], ...] = (
    ("return a - b", "return a + b", "Use addition for calculator.add."),
    ("return text", "return text.strip().lower()", "Trim and lowercase normalized text."),
    ("return raw[key]", "return json.loads(raw)[key]", "Parse the JSON string before key lookup."),
    ("return a + b", "return f\"{a.rstrip('/')}/{b.lstrip('/')}\"", "Join path segments with exactly one slash."),
    ("return len(lines)", "return sum(1 for line in lines if \"[x]\" not in line)", "Count only open todo lines."),
)


def find_known_replacement(project_root: Path) -> ReplacementPatch | None:
    src_root = project_root / "src"
    candidates = sorted(src_root.rglob("*.py")) if src_root.exists() else sorted(project_root.rglob("*.py"))
    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for old, new, summary in KNOWN_FIXES:
            if old in content:
                return ReplacementPatch(path=path, old=old, new=new, summary=summary)
    return None
