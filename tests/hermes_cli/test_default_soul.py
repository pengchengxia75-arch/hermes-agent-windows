from hermes_cli.config import _ensure_default_soul_md
from hermes_cli.default_soul import DEFAULT_SOUL_MD, LEGACY_DEFAULT_SOUL_MD, should_upgrade_legacy_soul


def test_default_soul_explicitly_uses_hermes_identity():
    assert "Hermes Agent" in DEFAULT_SOUL_MD
    assert "Do not claim to be Claude Code" in DEFAULT_SOUL_MD


def test_legacy_default_soul_is_detected_for_upgrade():
    assert should_upgrade_legacy_soul(LEGACY_DEFAULT_SOUL_MD)


def test_ensure_default_soul_upgrades_legacy_template(tmp_path):
    soul_path = tmp_path / "SOUL.md"
    soul_path.write_text(LEGACY_DEFAULT_SOUL_MD, encoding="utf-8")

    _ensure_default_soul_md(tmp_path)

    assert soul_path.read_text(encoding="utf-8") == DEFAULT_SOUL_MD
