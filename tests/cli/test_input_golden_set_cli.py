from jarvis import cli as cli_mod


def _run_once(text: str) -> str:
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    return cli_mod._handle_natural_language(state, text)


def test_cli_greeting_does_not_clarify():
    out = _run_once("你好啊")
    assert "我需要再确认一下" not in out
    assert "创建/修改代码文件" not in out
    assert "Task task_" not in out


def test_cli_context_slash_does_not_enter_llm():
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    out = cli_mod._handle_slash_command(state, "/context")
    assert out is not None
    assert "Unknown command" not in out


def test_cli_unix_path_is_not_unknown_command():
    out = _run_once("/Users/a/file.py")
    assert "Unknown command" not in out


def test_cli_task_args_preserved_in_parser():
    from src.jarvis.core.routing.input_gateway import build_input_envelope

    envelope = build_input_envelope("/task 115")
    assert envelope.slash.raw_args == "115"
