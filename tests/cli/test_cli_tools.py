from argparse import Namespace

import jarvis
from jarvis import cli as cli_mod


def test_cli_tools_command_lists_tools(monkeypatch):
    monkeypatch.setattr(jarvis, "bootstrap", lambda: (_ for _ in ()).throw(SystemExit("test fallback")))
    args = Namespace(call=None, category=None, extra=[])
    cli_mod.cmd_tools(args)
