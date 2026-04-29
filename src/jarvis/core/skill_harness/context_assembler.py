"""Skill context assembly for runtime prompt/context input."""

from __future__ import annotations

from time import perf_counter

from ..result import ok_result


class SkillContextAssembler:
    def assemble(
        self,
        *,
        matched_skills: list[dict],
        registry_snapshot: list[dict],
        context_budget_chars: int = 2000,
        max_active_skills: int = 3,
    ) -> dict:
        started = perf_counter()
        entry_map = {entry.get("skill_id"): entry for entry in registry_snapshot}
        budget = max(200, int(context_budget_chars))
        selected = []
        blocks = []
        consumed = 0

        for match in matched_skills[: max(1, max_active_skills)]:
            skill_id = match.get("skill_id")
            entry = entry_map.get(skill_id)
            if not entry:
                continue
            block = self._to_instruction_block(entry)
            projected = consumed + len(block)
            if projected > budget:
                break
            selected.append(skill_id)
            blocks.append(block)
            consumed = projected

        return ok_result(
            {
                "active_skill_ids": selected,
                "active_skills_summary": [entry_map[sid]["skill_name"] for sid in selected if sid in entry_map],
                "instruction_block": "\n\n".join(blocks),
                "budget_chars": budget,
                "consumed_chars": consumed,
                "budget_exhausted": consumed >= budget,
            },
            started,
        )

    @staticmethod
    def _to_instruction_block(entry: dict) -> str:
        required = ", ".join(entry.get("required_tools") or []) or "none"
        tags = ", ".join(entry.get("tags") or []) or "none"
        desc = entry.get("description") or ""
        return (
            f"[Skill:{entry.get('skill_id')}]\\n"
            f"name={entry.get('skill_name')}\\n"
            f"required_tools={required}\\n"
            f"tags={tags}\\n"
            f"guidance={desc}"
        )
