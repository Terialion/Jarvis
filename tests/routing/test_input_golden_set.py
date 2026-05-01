from src.jarvis.core.routing.golden_inputs import INPUT_GOLDEN_SET
from src.jarvis.core.routing.hybrid_router import route_user_input
from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.safety_gate import apply_route_safety


def test_input_golden_set():
    for item in INPUT_GOLDEN_SET:
        text = str(item["input"])
        if item.get("expected_kind") == "slash_command":
            envelope = build_input_envelope(text)
            assert envelope.slash.is_slash_command is True, text
            assert envelope.slash.command_name == item.get("expected_command_name"), text
            if "expected_raw_args" in item:
                assert envelope.slash.raw_args == item["expected_raw_args"], text
            continue
        if item.get("expected_kind") == "path":
            envelope = build_input_envelope(text)
            assert envelope.slash.is_slash_command is False, text
            assert envelope.slash.looks_like_path is True, text
            continue

        routed = route_user_input(text, source_surface="cli", input_kind="unknown_task")
        safe = apply_route_safety(routed, text, mode="safe")
        assert safe.response_mode == item["expected_response_mode"], text
        if "expected_intent" in item:
            assert safe.intent == item["expected_intent"], text
        if "requires_repo_read" in item:
            assert safe.requires_repo_read is item["requires_repo_read"], text
        if "requires_write" in item:
            assert safe.requires_write is item["requires_write"], text
        if "requires_shell" in item:
            assert safe.requires_shell is item["requires_shell"], text
        if "requires_approval" in item:
            assert safe.requires_approval is item["requires_approval"], text
