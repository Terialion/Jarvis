from argparse import Namespace


class _ClosedStream:
    closed = True

    def write(self, _msg):
        raise ValueError("I/O operation on closed file.")

    def flush(self):
        raise ValueError("I/O operation on closed file.")


def test_cmd_tools_handles_bootstrap_failure_with_closed_stderr(monkeypatch):
    import jarvis
    from jarvis import cli as cli_mod

    monkeypatch.setattr(jarvis, "bootstrap", lambda: (_ for _ in ()).throw(ValueError("bootstrap failed")))
    monkeypatch.setattr("sys.stderr", _ClosedStream(), raising=False)

    args = Namespace(call=None, category=None, extra=[])
    cli_mod.cmd_tools(args)

