from hermes_cli.default_soul import DEFAULT_SOUL_MD


def test_default_soul_explicitly_uses_hermes_identity():
    assert "Hermes Agent" in DEFAULT_SOUL_MD
    assert "Do not claim to be Claude Code" in DEFAULT_SOUL_MD
