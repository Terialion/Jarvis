def test_cli_does_not_require_legacy_web_search():
    import jarvis.cli

    assert jarvis.cli is not None
