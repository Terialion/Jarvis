from argparse import Namespace

from jarvis import cli as cli_mod


def test_cli_approvals_list_mock_path():
    args = Namespace(approval_cmd="list", api_base="http://127.0.0.1:1")
    assert cli_mod.cmd_approvals(args) == 0

