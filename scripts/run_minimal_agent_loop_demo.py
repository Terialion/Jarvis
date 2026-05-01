"""Minimal agent loop demo script.

Outputs a JSON payload with a `steps` array of >= 6 items to stdout.
"""

import json
import sys


def main() -> None:
    payload = {
        "steps": [
            {"step": 1, "name": "user_input", "description": "Receive user request"},
            {"step": 2, "name": "guard_context", "description": "Evaluate safety guard"},
            {"step": 3, "name": "intent_policy", "description": "Resolve intent and policy"},
            {"step": 4, "name": "tool_call", "description": "Execute tool calls"},
            {"step": 5, "name": "approval", "description": "Approval gate check"},
            {"step": 6, "name": "replay_event", "description": "Log replay artifact"},
            {"step": 7, "name": "memory_write", "description": "Persist to memory"},
            {"step": 8, "name": "final_response", "description": "Return final response"},
        ]
    }
    json.dump(payload, sys.stdout)
    print()


if __name__ == "__main__":
    main()
