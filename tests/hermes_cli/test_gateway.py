"""Tests for hermes_cli.gateway."""

import signal
from types import SimpleNamespace
from unittest.mock import patch, call

import hermes_cli.gateway as gateway


class TestSystemdLingerStatus:
    def test_reports_enabled(self, monkeypatch):
        monkeypatch.setattr(gateway, "is_linux", lambda: True)
        monkeypatch.setenv("USER", "alice")
        monkeypatch.setattr(
            gateway.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="yes\n", stderr=""),
        )
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/loginctl")

        assert gateway.get_systemd_linger_status() == (True, "")

    def test_reports_disabled(self, monkeypatch):
        monkeypatch.setattr(gateway, "is_linux", lambda: True)
        monkeypatch.setenv("USER", "alice")
        monkeypatch.setattr(
            gateway.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="no\n", stderr=""),
        )
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/loginctl")

        assert gateway.get_systemd_linger_status() == (False, "")


def test_systemd_status_warns_when_linger_disabled(monkeypatch, tmp_path, capsys):
    unit_path = tmp_path / "hermes-gateway.service"
    unit_path.write_text("[Unit]\n")

    monkeypatch.setattr(gateway, "get_systemd_unit_path", lambda system=False: unit_path)
    monkeypatch.setattr(gateway, "get_systemd_linger_status", lambda: (False, ""))

    def fake_run(cmd, capture_output=False, text=False, check=False, **kwargs):
        if cmd[:4] == ["systemctl", "--user", "status", gateway.get_service_name()]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["systemctl", "--user", "is-active"]:
            return SimpleNamespace(returncode=0, stdout="active\n", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(gateway.subprocess, "run", fake_run)

    gateway.systemd_status(deep=False)

    out = capsys.readouterr().out
    assert "gateway service is running" in out
    assert "Systemd linger is disabled" in out
    assert "loginctl enable-linger" in out


def test_systemd_install_checks_linger_status(monkeypatch, tmp_path, capsys):
    unit_path = tmp_path / "systemd" / "user" / "hermes-gateway.service"

    monkeypatch.setattr(gateway, "get_systemd_unit_path", lambda system=False: unit_path)

    calls = []
    helper_calls = []

    def fake_run(cmd, check=False, **kwargs):
        calls.append((cmd, check))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(gateway.subprocess, "run", fake_run)
    monkeypatch.setattr(gateway, "_ensure_linger_enabled", lambda: helper_calls.append(True))

    gateway.systemd_install(force=False)

    out = capsys.readouterr().out
    assert unit_path.exists()
    assert [cmd for cmd, _ in calls] == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", gateway.get_service_name()],
    ]
    assert helper_calls == [True]
    assert "User service installed and enabled" in out


def test_systemd_install_system_scope_skips_linger_and_uses_systemctl(monkeypatch, tmp_path, capsys):
    unit_path = tmp_path / "etc" / "systemd" / "system" / "hermes-gateway.service"

    monkeypatch.setattr(gateway, "get_systemd_unit_path", lambda system=False: unit_path)
    monkeypatch.setattr(
        gateway,
        "generate_systemd_unit",
        lambda system=False, run_as_user=None: f"scope={system} user={run_as_user}\n",
    )
    monkeypatch.setattr(gateway, "_require_root_for_system_service", lambda action: None)

    calls = []
    helper_calls = []

    def fake_run(cmd, check=False, **kwargs):
        calls.append((cmd, check))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(gateway.subprocess, "run", fake_run)
    monkeypatch.setattr(gateway, "_ensure_linger_enabled", lambda: helper_calls.append(True))

    gateway.systemd_install(force=False, system=True, run_as_user="alice")

    out = capsys.readouterr().out
    assert unit_path.exists()
    assert unit_path.read_text(encoding="utf-8") == "scope=True user=alice\n"
    assert [cmd for cmd, _ in calls] == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", gateway.get_service_name()],
    ]
    assert helper_calls == []
    assert "Configured to run as: alice" not in out  # generated test unit has no User= line
    assert "System service installed and enabled" in out


def test_conflicting_systemd_units_warning(monkeypatch, tmp_path, capsys):
    user_unit = tmp_path / "user" / "hermes-gateway.service"
    system_unit = tmp_path / "system" / "hermes-gateway.service"
    user_unit.parent.mkdir(parents=True)
    system_unit.parent.mkdir(parents=True)
    user_unit.write_text("[Unit]\n", encoding="utf-8")
    system_unit.write_text("[Unit]\n", encoding="utf-8")

    monkeypatch.setattr(
        gateway,
        "get_systemd_unit_path",
        lambda system=False: system_unit if system else user_unit,
    )

    gateway.print_systemd_scope_conflict_warning()

    out = capsys.readouterr().out
    assert "Both user and system gateway services are installed" in out
    assert "hermes gateway uninstall" in out
    assert "--system" in out


def test_install_linux_gateway_from_setup_system_choice_without_root_prints_followup(monkeypatch, capsys):
    monkeypatch.setattr(gateway, "prompt_linux_gateway_install_scope", lambda: "system")
    monkeypatch.setattr(gateway.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(gateway, "_default_system_service_user", lambda: "alice")
    monkeypatch.setattr(gateway, "systemd_install", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not install")))

    scope, did_install = gateway.install_linux_gateway_from_setup(force=False)

    out = capsys.readouterr().out
    assert (scope, did_install) == ("system", False)
    assert "sudo hermes gateway install --system --run-as-user alice" in out
    assert "sudo hermes gateway start --system" in out


def test_install_linux_gateway_from_setup_system_choice_as_root_installs(monkeypatch):
    monkeypatch.setattr(gateway, "prompt_linux_gateway_install_scope", lambda: "system")
    monkeypatch.setattr(gateway.os, "geteuid", lambda: 0)
    monkeypatch.setattr(gateway, "_default_system_service_user", lambda: "alice")

    calls = []
    monkeypatch.setattr(
        gateway,
        "systemd_install",
        lambda force=False, system=False, run_as_user=None: calls.append((force, system, run_as_user)),
    )

    scope, did_install = gateway.install_linux_gateway_from_setup(force=True)

    assert (scope, did_install) == ("system", True)
    assert calls == [(True, True, "alice")]


# ---------------------------------------------------------------------------
# _wait_for_gateway_exit
# ---------------------------------------------------------------------------


class TestWaitForGatewayExit:
    """PID-based wait with force-kill on timeout."""

    def test_returns_immediately_when_no_pid(self, monkeypatch):
        """If get_running_pid returns None, exit instantly."""
        monkeypatch.setattr("gateway.status.get_running_pid", lambda: None)
        # Should return without sleeping at all.
        gateway._wait_for_gateway_exit(timeout=1.0, force_after=0.5)

    def test_returns_when_process_exits_gracefully(self, monkeypatch):
        """Process exits after a couple of polls 鈥?no SIGKILL needed."""
        poll_count = 0

        def mock_get_running_pid():
            nonlocal poll_count
            poll_count += 1
            return 12345 if poll_count <= 2 else None

        monkeypatch.setattr("gateway.status.get_running_pid", mock_get_running_pid)
        monkeypatch.setattr("time.sleep", lambda _: None)

        gateway._wait_for_gateway_exit(timeout=10.0, force_after=999.0)
        # Should have polled until None was returned.
        assert poll_count == 3

    def test_force_kills_after_grace_period(self, monkeypatch):
        """When the process doesn't exit, SIGKILL the saved PID."""
        import time as _time

        # Simulate monotonic time advancing past force_after
        call_num = 0
        def fake_monotonic():
            nonlocal call_num
            call_num += 1
            # First two calls: initial deadline + force_deadline setup (time 0)
            # Then each loop iteration advances time
            return call_num * 2.0  # 2, 4, 6, 8, ...

        kills = []
        def mock_kill(pid, sig):
            kills.append((pid, sig))

        # get_running_pid returns the PID until kill is sent, then None
        def mock_get_running_pid():
            return None if kills else 42

        monkeypatch.setattr("time.monotonic", fake_monotonic)
        monkeypatch.setattr("time.sleep", lambda _: None)
        monkeypatch.setattr("gateway.status.get_running_pid", mock_get_running_pid)
        monkeypatch.setattr("os.kill", mock_kill)

        gateway._wait_for_gateway_exit(timeout=10.0, force_after=5.0)
        assert (42, signal.SIGKILL) in kills

    def test_handles_process_already_gone_on_kill(self, monkeypatch):
        """ProcessLookupError during SIGKILL is not fatal."""
        import time as _time

        call_num = 0
        def fake_monotonic():
            nonlocal call_num
            call_num += 1
            return call_num * 3.0  # Jump past force_after quickly

        def mock_kill(pid, sig):
            raise ProcessLookupError

        monkeypatch.setattr("time.monotonic", fake_monotonic)
        monkeypatch.setattr("time.sleep", lambda _: None)
        monkeypatch.setattr("gateway.status.get_running_pid", lambda: 99)
        monkeypatch.setattr("os.kill", mock_kill)

        # Should not raise 鈥?ProcessLookupError means it's already gone.
        gateway._wait_for_gateway_exit(timeout=10.0, force_after=2.0)


def test_status_running_on_windows_shows_foreground_hint(monkeypatch, capsys):
    monkeypatch.setattr(gateway, "is_linux", lambda: False)
    monkeypatch.setattr(gateway, "is_macos", lambda: False)
    monkeypatch.setattr(gateway, "is_windows", lambda: True)
    monkeypatch.setattr(gateway, "find_gateway_pids", lambda exclude_pids=None: [1234])

    gateway.gateway_command(SimpleNamespace(gateway_command="status", deep=False))

    out = capsys.readouterr().out
    assert "Gateway is running" in out
    assert "Run directly on Windows:" in out
    assert "hermes gateway          # Run in foreground" in out
    assert "hermes gateway install" not in out


def test_status_not_running_on_windows_omits_service_install_hint(monkeypatch, capsys):
    monkeypatch.setattr(gateway, "is_linux", lambda: False)
    monkeypatch.setattr(gateway, "is_macos", lambda: False)
    monkeypatch.setattr(gateway, "is_windows", lambda: True)
    monkeypatch.setattr(gateway, "find_gateway_pids", lambda exclude_pids=None: [])
    monkeypatch.setattr(gateway, "_runtime_health_lines", lambda: [])

    gateway.gateway_command(SimpleNamespace(gateway_command="status", deep=False))

    out = capsys.readouterr().out
    assert "Gateway is not running" in out
    assert "hermes gateway          # Run in foreground" in out
    assert "hermes gateway install" not in out
    assert "sudo hermes gateway install --system" not in out


def test_feishu_platform_label_and_vars_present():
    feishu_platform = next(p for p in gateway._PLATFORMS if p["key"] == "feishu")
    assert feishu_platform["label"] == "Feishu / Lark / 飞书"
    var_names = [v["name"] for v in feishu_platform["vars"]]
    assert "FEISHU_APP_ID" in var_names
    assert "FEISHU_APP_SECRET" in var_names
    assert "FEISHU_CONNECTION_MODE" in var_names


def test_wecom_platform_label_and_vars_present():
    wecom_platform = next(p for p in gateway._PLATFORMS if p["key"] == "wecom")
    assert wecom_platform["label"] == "WeCom (Enterprise WeChat) / 企业微信"
    var_names = [v["name"] for v in wecom_platform["vars"]]
    assert "WECOM_BOT_ID" in var_names
    assert "WECOM_SECRET" in var_names
    assert "WECOM_ALLOWED_USERS" in var_names


def test_qq_platform_label_and_vars_present():
    qq_platform = next(p for p in gateway._PLATFORMS if p["key"] == "qq")
    assert qq_platform["label"] == "QQ / OneBot / QQ机器人"
    var_names = [v["name"] for v in qq_platform["vars"]]
    assert "QQ_ONEBOT_URL" in var_names
    assert "QQ_ONEBOT_ACCESS_TOKEN" in var_names
    assert "QQ_HOME_CHANNEL" in var_names


def test_setup_standard_platform_saves_feishu_values(monkeypatch):
    platform = next(p for p in gateway._PLATFORMS if p["key"] == "feishu")
    prompts = iter(["cli_app", "secret_app", "feishu", "websocket", "ou_alice", "oc_home"])
    saved: list[tuple[str, str]] = []

    monkeypatch.setattr(gateway, "get_env_value", lambda name: "")
    monkeypatch.setattr(gateway, "prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr(gateway, "prompt_yes_no", lambda *args, **kwargs: True)
    monkeypatch.setattr(gateway, "save_env_value", lambda name, value: saved.append((name, value)))

    gateway._setup_standard_platform(platform)

    assert ("FEISHU_APP_ID", "cli_app") in saved
    assert ("FEISHU_APP_SECRET", "secret_app") in saved
    assert ("FEISHU_CONNECTION_MODE", "websocket") in saved
    assert ("FEISHU_ALLOWED_USERS", "ou_alice") in saved


def test_setup_standard_platform_saves_wecom_values(monkeypatch):
    platform = next(p for p in gateway._PLATFORMS if p["key"] == "wecom")
    prompts = iter(["bot_123", "secret_456", "user_a,user_b", "group_home"])
    saved: list[tuple[str, str]] = []

    monkeypatch.setattr(gateway, "get_env_value", lambda name: "")
    monkeypatch.setattr(gateway, "prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr(gateway, "prompt_yes_no", lambda *args, **kwargs: True)
    monkeypatch.setattr(gateway, "save_env_value", lambda name, value: saved.append((name, value)))

    gateway._setup_standard_platform(platform)

    assert ("WECOM_BOT_ID", "bot_123") in saved
    assert ("WECOM_SECRET", "secret_456") in saved
    assert ("WECOM_ALLOWED_USERS", "user_a,user_b") in saved
    assert ("WECOM_HOME_CHANNEL", "group_home") in saved


def test_setup_standard_platform_saves_qq_values(monkeypatch):
    platform = next(p for p in gateway._PLATFORMS if p["key"] == "qq")
    prompts = iter(["ws://127.0.0.1:3001", "bridge_token", "group_admin,user_owner", "group:123456"])
    saved: list[tuple[str, str]] = []

    monkeypatch.setattr(gateway, "get_env_value", lambda name: "")
    monkeypatch.setattr(gateway, "prompt", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr(gateway, "prompt_yes_no", lambda *args, **kwargs: True)
    monkeypatch.setattr(gateway, "save_env_value", lambda name, value: saved.append((name, value)))

    gateway._setup_standard_platform(platform)

    assert ("QQ_ONEBOT_URL", "ws://127.0.0.1:3001") in saved
    assert ("QQ_ONEBOT_ACCESS_TOKEN", "bridge_token") in saved
    assert ("QQ_ALLOWED_USERS", "group_admin,user_owner") in saved
    assert ("QQ_HOME_CHANNEL", "group:123456") in saved


def test_gateway_setup_on_windows_runs_feishu_flow_and_prints_foreground_hint(monkeypatch, capsys):
    saved = {}
    feishu_index = next(i for i, p in enumerate(gateway._PLATFORMS) if p["key"] == "feishu")
    choices = iter([feishu_index, len(gateway._PLATFORMS)])
    calls = []

    monkeypatch.setattr(gateway, "is_managed", lambda: False)
    monkeypatch.setattr(gateway, "is_linux", lambda: False)
    monkeypatch.setattr(gateway, "is_macos", lambda: False)
    monkeypatch.setattr(gateway, "is_windows", lambda: True)
    monkeypatch.setattr(gateway, "_is_service_installed", lambda: False)
    monkeypatch.setattr(gateway, "_is_service_running", lambda: False)
    monkeypatch.setattr(gateway, "print_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(gateway, "print_info", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_success", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_warning", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_error", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "color", lambda text, *_args, **_kwargs: text)
    monkeypatch.setattr(gateway, "prompt_choice", lambda *args, **kwargs: next(choices))
    monkeypatch.setattr(gateway, "prompt_yes_no", lambda *args, **kwargs: False)
    monkeypatch.setattr(gateway, "get_env_value", lambda name: saved.get(name, ""))

    def fake_setup(platform):
        calls.append(platform["key"])
        saved[platform["token_var"]] = "configured"

    monkeypatch.setattr(gateway, "_setup_standard_platform", fake_setup)

    gateway.gateway_setup()

    out = capsys.readouterr().out
    assert calls == ["feishu"]
    assert "Gateway service is not installed yet." in out
    assert "Run in foreground: hermes gateway" in out


def test_gateway_setup_on_windows_runs_wecom_flow_and_prints_foreground_hint(monkeypatch, capsys):
    saved = {}
    wecom_index = next(i for i, p in enumerate(gateway._PLATFORMS) if p["key"] == "wecom")
    choices = iter([wecom_index, len(gateway._PLATFORMS)])
    calls = []

    monkeypatch.setattr(gateway, "is_managed", lambda: False)
    monkeypatch.setattr(gateway, "is_linux", lambda: False)
    monkeypatch.setattr(gateway, "is_macos", lambda: False)
    monkeypatch.setattr(gateway, "is_windows", lambda: True)
    monkeypatch.setattr(gateway, "_is_service_installed", lambda: False)
    monkeypatch.setattr(gateway, "_is_service_running", lambda: False)
    monkeypatch.setattr(gateway, "print_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(gateway, "print_info", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_success", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_warning", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_error", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "color", lambda text, *_args, **_kwargs: text)
    monkeypatch.setattr(gateway, "prompt_choice", lambda *args, **kwargs: next(choices))
    monkeypatch.setattr(gateway, "prompt_yes_no", lambda *args, **kwargs: False)
    monkeypatch.setattr(gateway, "get_env_value", lambda name: saved.get(name, ""))

    def fake_setup(platform):
        calls.append(platform["key"])
        saved[platform["token_var"]] = "configured"

    monkeypatch.setattr(gateway, "_setup_standard_platform", fake_setup)

    gateway.gateway_setup()

    out = capsys.readouterr().out
    assert calls == ["wecom"]
    assert "Gateway service is not installed yet." in out
    assert "Run in foreground: hermes gateway" in out


def test_gateway_setup_on_windows_runs_qq_flow_and_prints_foreground_hint(monkeypatch, capsys):
    saved = {}
    qq_index = next(i for i, p in enumerate(gateway._PLATFORMS) if p["key"] == "qq")
    choices = iter([qq_index, len(gateway._PLATFORMS)])
    calls = []

    monkeypatch.setattr(gateway, "is_managed", lambda: False)
    monkeypatch.setattr(gateway, "is_linux", lambda: False)
    monkeypatch.setattr(gateway, "is_macos", lambda: False)
    monkeypatch.setattr(gateway, "is_windows", lambda: True)
    monkeypatch.setattr(gateway, "_is_service_installed", lambda: False)
    monkeypatch.setattr(gateway, "_is_service_running", lambda: False)
    monkeypatch.setattr(gateway, "print_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(gateway, "print_info", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_success", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_warning", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "print_error", lambda *args, **kwargs: print(*args))
    monkeypatch.setattr(gateway, "color", lambda text, *_args, **_kwargs: text)
    monkeypatch.setattr(gateway, "prompt_choice", lambda *args, **kwargs: next(choices))
    monkeypatch.setattr(gateway, "prompt_yes_no", lambda *args, **kwargs: False)
    monkeypatch.setattr(gateway, "get_env_value", lambda name: saved.get(name, ""))

    def fake_setup(platform):
        calls.append(platform["key"])
        saved[platform["token_var"]] = "configured"

    monkeypatch.setattr(gateway, "_setup_standard_platform", fake_setup)

    gateway.gateway_setup()

    out = capsys.readouterr().out
    assert calls == ["qq"]
    assert "Gateway service is not installed yet." in out
    assert "Run in foreground: hermes gateway" in out
