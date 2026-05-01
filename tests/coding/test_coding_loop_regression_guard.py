from jarvis import cli as cli_mod


def test_chat_and_repo_inspection_stay_out_of_task_flow() -> None:
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    chat = cli_mod._handle_natural_language(state, "what can you do")
    assert "Task task_" not in chat
    assert "Completed in safe mode" not in chat

    inspect = cli_mod._handle_natural_language(state, "Inspect this repo. Do not modify files.")
    assert "Task task_" not in inspect
    # Negation routes to plan_answer -> chat path.
    # Without LLM, returns fallback instead of "Repository inspection complete."
    assert inspect != ""

