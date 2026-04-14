from hermes_cli.gateway import _runtime_health_lines


def test_runtime_health_lines_include_fatal_platform_and_startup_reason(monkeypatch):
    monkeypatch.setattr(
        "gateway.status.read_runtime_status",
        lambda: {
            "gateway_state": "startup_failed",
            "exit_reason": "telegram conflict",
            "platforms": {
                "telegram": {
                    "state": "fatal",
                    "error_message": "another poller is active",
                }
            },
        },
    )

    lines = _runtime_health_lines()

    assert "[WARN] telegram: another poller is active" in lines
    assert "[WARN] Last startup issue: telegram conflict" in lines


def test_runtime_health_lines_include_shutdown_reason(monkeypatch):
    monkeypatch.setattr(
        "gateway.status.read_runtime_status",
        lambda: {
            "gateway_state": "stopped",
            "exit_reason": "manual stop",
            "platforms": {},
        },
    )

    lines = _runtime_health_lines()

    assert "[WARN] Last shutdown reason: manual stop" in lines

