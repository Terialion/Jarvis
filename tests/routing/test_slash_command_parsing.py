import pytest

from src.jarvis.core.routing.input_gateway import build_input_envelope


@pytest.mark.parametrize(
    ("text", "command_name", "raw_args", "args_tokens"),
    [
        ("/help", "help", "", []),
        ("/context", "context", "", []),
        ("/task 115", "task", "115", ["115"]),
        ("/skill python-debug fix greeting bug", "skill", "python-debug fix greeting bug", ["python-debug", "fix", "greeting", "bug"]),
        ("/unknown abc", "unknown", "abc", ["abc"]),
    ],
)
def test_slash_parsing_keeps_command_and_args(text: str, command_name: str, raw_args: str, args_tokens: list[str]) -> None:
    envelope = build_input_envelope(text)
    assert envelope.slash.is_slash_command is True
    assert envelope.slash.command_name == command_name
    assert envelope.slash.raw_args == raw_args
    assert envelope.slash.args_tokens == args_tokens


def test_unknown_slash_marked_unknown():
    envelope = build_input_envelope("/unknown abc")
    assert envelope.slash.is_unknown_command is True
