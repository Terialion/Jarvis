from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.skill_command_router import route_skill_command


def test_skill_command_tool_dispatch_requires_approval():
    registry_items = [
        {
            "skill_id": "python-debug",
            "id": "python-debug",
            "description": "Debug Python issues.",
            "metadata": {
                "command_name": "python-debug",
                "command_dispatch": "tool",
                "command_tool": "python_debug_tool",
                "risk_level": "high",
                "user_invocable": True,
            },
        }
    ]
    route = route_skill_command(build_input_envelope("/python-debug fix greeting bug"), registry_items=registry_items)
    assert route.handled is True
    assert route.response_mode == "skill_tool_dispatch"
    assert route.requires_approval is True
    assert route.requires_tools == ["python_debug_tool"]


def test_skill_command_model_dispatch_injects_context():
    registry_items = [
        {
            "skill_id": "python-debug",
            "id": "python-debug",
            "description": "Debug Python issues.",
            "metadata": {
                "command_name": "python-debug",
                "command_dispatch": "model",
                "risk_level": "medium",
                "user_invocable": True,
            },
        }
    ]
    route = route_skill_command(build_input_envelope("/skill python-debug fix greeting bug"), registry_items=registry_items)
    assert route.handled is True
    assert route.response_mode == "skill_agent"
    assert route.inject_skill_context is True
    assert route.raw_args == "fix greeting bug"
