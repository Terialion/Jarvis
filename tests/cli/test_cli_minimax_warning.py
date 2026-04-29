from argparse import Namespace

import jarvis
from jarvis import cli as cli_mod

def test_missing_minimax_config_is_warning_not_crash(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_BASE", raising=False)
    monkeypatch.setattr(jarvis, "bootstrap", lambda: (_ for _ in ()).throw(SystemExit("test fallback")))
    args = Namespace(call=None, category=None, extra=[])
    cli_mod.cmd_tools(args)
