from jarvis import cli as cli_mod


def test_repo_inspection_dispatch_not_task_flow():
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    out = cli_mod._handle_natural_language(state, "帮我看看这个项目结构，不要修改")
    assert "Task task_" not in out
    # Negation ("不要修改") routes to plan_answer -> chat path.
    # Without LLM, returns fallback instead of "Repository inspection complete."
    assert out != ""
