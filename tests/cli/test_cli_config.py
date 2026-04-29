from argparse import Namespace

from jarvis import cli as cli_mod


def test_cli_config_show_runs():
    args = Namespace(show=True, set=None, encrypt=False)
    cli_mod.cmd_config(args)

