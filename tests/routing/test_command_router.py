from src.jarvis.core.routing.command_router import route_command
from src.jarvis.core.routing.input_gateway import build_input_envelope


def test_help_command_routed_without_llm():
    route = route_command(build_input_envelope("/help"))
    assert route.handled is True
    assert route.command_name == "help"
    assert route.entered_llm is False


def test_context_command_routed_without_llm():
    route = route_command(build_input_envelope("/context"))
    assert route.handled is True
    assert route.command_name == "context"
    assert route.entered_llm is False


def test_unknown_command_returns_hint_without_llm():
    route = route_command(build_input_envelope("/unknown abc"))
    assert route.handled is True
    assert route.command_name == "unknown"
    assert route.entered_llm is False
    assert "Unknown command" in route.message


def test_task_command_keeps_raw_args():
    route = route_command(build_input_envelope("/task 115"))
    assert route.command_name == "task"
    assert route.raw_args == "115"
    assert route.args_tokens == ["115"]
