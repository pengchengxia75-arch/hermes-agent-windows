import sys

from hermes_cli import setup as setup_mod


def test_offer_launch_chat_spawns_fresh_process(monkeypatch):
    launched = {}

    monkeypatch.setattr(setup_mod, "prompt_yes_no", lambda *args, **kwargs: True)

    def fake_run(cmd, check=False):
        launched["cmd"] = cmd
        launched["check"] = check
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    setup_mod._offer_launch_chat()

    assert launched["cmd"] == [sys.executable, "-m", "hermes_cli.main"]
    assert launched["check"] is False
