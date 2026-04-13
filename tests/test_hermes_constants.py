from pathlib import Path

from hermes_constants import get_hermes_home


def test_get_hermes_home_prefers_managed_windows_home_when_present(monkeypatch, tmp_path):
    managed_home = tmp_path / "LocalAppData" / "hermes"
    managed_home.mkdir(parents=True)

    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    assert get_hermes_home() == managed_home


def test_get_hermes_home_falls_back_to_dot_hermes_when_managed_home_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "UserProfile"))

    assert get_hermes_home() == Path(str(tmp_path / "UserProfile")) / ".hermes"
