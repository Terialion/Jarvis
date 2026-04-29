from argparse import Namespace

from jarvis import cli as cli_mod


def test_cli_server_dry_run_start():
    args = Namespace(server_cmd="start", host="127.0.0.1", port=8765, dry_run=True)
    assert cli_mod.cmd_server(args) == 0

