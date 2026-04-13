from hermes_cli import setup as setup_mod


def test_prompt_choice_on_windows_uses_numbered_menu(monkeypatch, capsys):
    monkeypatch.setattr(setup_mod.os, "name", "nt", raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    result = setup_mod.prompt_choice(
        "Select provider:",
        [
            "MiniMax / MiniMax（国际站直连）",
            "MiniMax China / MiniMax China（国内站直连）",
        ],
        default=0,
    )

    out = capsys.readouterr().out
    assert "1. MiniMax" in out
    assert "2. MiniMax China" in out
    assert result == 1
