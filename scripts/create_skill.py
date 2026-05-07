from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

from src.jarvis.skills.authoring import create_skill


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Jarvis skill template.")
    parser.add_argument("name", help="Skill name")
    parser.add_argument("--tools", default="Read", help="allowed-tools value")
    parser.add_argument("--tags", default="example", help="Single default tag")
    parser.add_argument("--description", default=None, help="Optional skill description")
    args = parser.parse_args()

    try:
        path = create_skill(
            args.name,
            base_dir=Path(".jarvis") / "skills",
            description=args.description,
            allowed_tools=args.tools,
            tag=args.tags,
        )
    except FileExistsError:
        print(f"Skill already exists: .jarvis/skills/{args.name}/SKILL.md")
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1

    print(f"Created skill template: {path.relative_to(Path.cwd())}")
    print("Next: edit description, allowed-tools, workflow, safety rules, and examples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
