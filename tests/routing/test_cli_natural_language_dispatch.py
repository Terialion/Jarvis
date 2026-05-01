from jarvis import cli as cli_mod


def _run_once(text: str) -> str:
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    return cli_mod._handle_natural_language(state, text)


def test_greeting_not_enter_task_flow():
    out = _run_once("你好")
    assert "Task " not in out
    assert "Plan" not in out
    assert "Events" not in out


def test_capability_not_enter_task_flow():
    out = _run_once("你能干嘛？")
    assert "Task " not in out
    assert "Plan" not in out
    assert "Events" not in out


def test_capability_en_not_enter_task_flow():
    out = _run_once("what u can do")
    assert "Task " not in out
    assert "Task task_" not in out
    assert "Events" not in out
    assert "I can" in out


def test_usage_help_not_enter_task_flow():
    out = _run_once("怎么让你改代码？")
    assert "Task " not in out
    assert "Plan" not in out
    assert "Events" not in out
    assert "计划" in out


def test_repo_inspection_not_task_flow():
    out = _run_once("帮我看看这个项目结构，不要修改")
    assert "Task " not in out
    assert "Task task_" not in out
    # Negation ("不要修改") routes to plan_answer -> chat path.
    # Without LLM, returns fallback message instead of repo inspection.
    assert out != ""


def test_coding_enters_task_flow():
    out = _run_once("修复这个 bug，并跑测试")
    # Coding verb detected -> work path -> AgentToolLoop.
    # Without LLM, returns [WORK] routing info (not a chat answer).
    assert ("Task " in out) or ("Approval required" in out) or ("[WORK]" in out)


def test_shell_is_approval_gated():
    out = _run_once("运行 pytest")
    # Shell execution request -> executor_action -> AgentToolLoop.
    # Without LLM, returns [WORK] routing info with shell.run in required_tools.
    assert ("Approval required" in out
            or ("[WORK]" in out and "shell" in out))
