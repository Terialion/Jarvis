from __future__ import annotations


def build_capabilities_catalog() -> dict:
    return {
        "tools": [
            {"name": "repo_reader.search_files", "input_schema": {"type": "object"}},
            {"name": "file_editor.replace_text", "input_schema": {"type": "object"}},
            {"name": "command_runner.run", "input_schema": {"type": "object"}},
        ],
        "resources": [
            {"name": "task.replay", "schema": {"type": "object"}},
            {"name": "operator.dashboard", "schema": {"type": "object"}},
        ],
        "prompts": [
            {"name": "plan_mode", "schema": {"type": "object"}},
            {"name": "recover_mode", "schema": {"type": "object"}},
        ],
    }

