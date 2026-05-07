from jarvis import cli as cli_mod


def _run_once(text: str) -> str:
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    return cli_mod._handle_natural_language(state, text)


def test_greeting_not_enter_task_flow() -> None:
    out = _run_once("你好")
    assert "Task " not in out
    assert "Plan" not in out
    assert "Events" not in out


def test_capability_not_enter_task_flow() -> None:
    out = _run_once("你能做什么？")
    assert "Task " not in out
    assert "Plan" not in out
    assert "Events" not in out


def test_capability_en_not_enter_task_flow() -> None:
    out = _run_once("what u can do")
    assert "Task " not in out
    assert "Task task_" not in out
    assert "Events" not in out
    assert out != ""


def test_usage_help_not_enter_task_flow() -> None:
    out = _run_once("怎么让你改代码？")
    assert "Task " not in out
    assert "Plan" not in out
    assert "Events" not in out
    assert out != ""


def test_repo_inspection_not_task_flow() -> None:
    out = _run_once("帮我看看这个项目结构，不要修改")
    assert "Task " not in out
    assert "Task task_" not in out
    assert out != ""


def test_coding_enters_agentloop_contract() -> None:
    out = _run_once("修复这个 bug，并跑测试")
    assert "Task " not in out
    assert "Events" not in out
    assert out != ""
    assert ("pytest" in out.lower()) or ("stop_reason=" in out) or ("jarvis" in out.lower())


def test_shell_request_is_not_legacy_task_flow() -> None:
    out = _run_once("运行 pytest")
    assert "Task " not in out
    assert "Events" not in out
    assert out != ""
    assert ("stop_reason=" in out) or ("tool" in out.lower()) or ("pytest" in out.lower()) or ("jarvis" in out.lower())
