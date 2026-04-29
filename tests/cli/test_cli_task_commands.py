from argparse import Namespace

from jarvis import cli as cli_mod


def test_cli_task_run_mock_path():
    args = Namespace(
        task_cmd="run",
        input="Analyze this repo and suggest next steps.",
        mode="safe",
        allow_code_changes=False,
        max_commands=3,
        max_files_changed=0,
        require_approval=True,
        api_base="http://127.0.0.1:1",
    )
    assert cli_mod.cmd_task(args) == 0

