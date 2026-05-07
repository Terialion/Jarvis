from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

from src.jarvis.skills.authoring import format_skill_doctor, format_validation_result
from src.jarvis.skills.registry import SkillRegistry
from src.jarvis.skills.validator import SkillValidator, default_validation_mode_for_spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Jarvis and ecosystem skills without executing them.")
    parser.add_argument("--skill", help="Validate one discovered skill by name")
    parser.add_argument("--path", help="Validate a specific skill directory or SKILL.md path")
    parser.add_argument("--mode", choices=("strict", "compatibility"), help="Override validation mode")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    registry = SkillRegistry(project_root=Path.cwd())
    validator = SkillValidator()

    if args.path:
        mode = args.mode or "compatibility"
        result = validator.validate_path(args.path, mode=mode, source="external")
        return _emit_single(result, as_json=args.json)

    if args.skill:
        try:
            spec = registry.get(args.skill)
        except KeyError:
            if args.json:
                print(json.dumps({"ok": False, "skill_name": args.skill, "findings": [{"level": "error", "code": "skill_not_found", "message": args.skill}]}, ensure_ascii=False, indent=2))
            else:
                print(f"skill-not-found: {args.skill}")
            return 1
        mode = args.mode or default_validation_mode_for_spec(spec)
        result = validator.validate_spec(spec, mode=mode)
        return _emit_single(result, as_json=args.json)

    specs = registry.list_skills()
    results = [validator.validate_spec(spec, mode=args.mode or default_validation_mode_for_spec(spec)) for spec in specs]
    if args.json:
        print(json.dumps({"skills": [result.to_dict() for result in results]}, ensure_ascii=False, indent=2))
    else:
        print(format_skill_doctor(results, specs))
    return 0 if all(result.ok for result in results) else 1


def _emit_single(result, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_validation_result(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
