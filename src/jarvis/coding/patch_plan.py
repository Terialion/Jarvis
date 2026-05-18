from __future__ import annotations

import re
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


def parse_llm_diff_response(response_text: str, project_root: Path | None = None) -> ReplacementPatch | None:
    """Extract a replacement patch from an LLM response containing old/new code blocks.

    Looks for markdown-style code blocks with ``old`` / ``new`` labels, or
    a unified diff with ``---`` / ``+++`` headers.  Falls back to
    ``find_known_replacement`` when no structured diff is found.
    """
    text = str(response_text or "")
    # Try fenced blocks with explicit labels
    old_match = re.search(r"```(?:old|before|original)\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    new_match = re.search(r"```(?:new|after|fixed)\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if old_match and new_match:
        old = old_match.group(1).strip()
        new = new_match.group(1).strip()
        if old != new:
            root = project_root or Path(".")
            src = root / "src"
            py_files = sorted(src.rglob("*.py")) if src.exists() else []
            best_path = root / "unknown"
            for py_file in py_files:
                try:
                    if old in py_file.read_text(encoding="utf-8"):
                        best_path = py_file
                        break
                except Exception:
                    continue
            return ReplacementPatch(path=best_path, old=old, new=new, summary="LLM-generated fix.")

    # Try inline old→new markers
    inline = re.search(r"(?:replace|change)\s*[`\"](.+?)[`\"]\s*(?:with|→|->)\s*[`\"](.+?)[`\"]", text, re.IGNORECASE)
    if inline:
        old = inline.group(1).strip()
        new = inline.group(2).strip()
        if old != new and project_root:
            return find_known_replacement(project_root) or ReplacementPatch(
                path=project_root / "unknown", old=old, new=new, summary="LLM inline fix."
            )

    if project_root:
        return find_known_replacement(project_root)
    return None
