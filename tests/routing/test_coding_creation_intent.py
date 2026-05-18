import pytest

from src.jarvis.core.routing.hybrid_router import route_user_input


@pytest.mark.parametrize(
    ("text", "requires_shell"),
    [
        ("在这个工作空间写一个python程序，打印helloworld。", False),
        ("写一个 python 程序打印 helloworld", False),
        ("新建一个 hello.py，打印 hello world", False),
        ("write a python program that prints hello world", False),
        ("create hello.py and run it", True),
        ("写一个 python 程序打印 helloworld，并运行一下", True),
    ],
)
def test_coding_creation_routes_to_agent_tool_loop(text: str, requires_shell: bool) -> None:
    route = route_user_input(text, source_surface="cli", input_kind="unknown_task")
    assert route.intent == "coding_task"
    assert route.response_mode == "agent_tool_loop"
    assert route.requires_write is True
    assert route.requires_approval is True
    assert route.requires_shell is requires_shell


def test_non_code_writing_does_not_enter_agent_tool_loop() -> None:
    route = route_user_input("写一段说明", source_surface="cli", input_kind="unknown_task")
    assert route.intent == "clarify"
    assert route.response_mode == "clarify_question"


def test_read_project_stays_repo_inspection() -> None:
    route = route_user_input("read this project", source_surface="cli", input_kind="unknown_task")
    assert route.intent == "repo_inspection"
    assert route.response_mode == "repo_inspection"
