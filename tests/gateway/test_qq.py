import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from gateway.config import PlatformConfig
from gateway.platforms.qq import QQAdapter, check_qq_requirements


def test_check_qq_requirements_accepts_config_url():
    assert check_qq_requirements(PlatformConfig(enabled=True, extra={"url": "http://127.0.0.1:3000"})) is True


def test_parse_chat_target_accepts_explicit_group_and_user():
    adapter = QQAdapter(PlatformConfig(enabled=True, extra={"url": "http://127.0.0.1:3000"}))

    assert adapter._parse_chat_target("group:123456") == ("group", "123456")
    assert adapter._parse_chat_target("user:24680") == ("user", "24680")


def test_parse_chat_target_uses_default_target_type():
    group_adapter = QQAdapter(PlatformConfig(enabled=True, extra={"url": "http://127.0.0.1:3000"}))
    user_adapter = QQAdapter(
        PlatformConfig(enabled=True, extra={"url": "http://127.0.0.1:3000", "default_target_type": "user"})
    )

    assert group_adapter._parse_chat_target("123456") == ("group", "123456")
    assert user_adapter._parse_chat_target("24680") == ("user", "24680")


def test_extract_text_supports_segment_lists():
    assert QQAdapter._extract_text(
        [
            {"type": "text", "data": {"text": "hello "}},
            {"type": "text", "data": {"text": "qq"}},
            {"type": "image", "data": {"file": "x.png"}},
        ]
    ) == "hello qq"


@pytest.mark.asyncio
async def test_send_posts_to_real_onebot_group_endpoint():
    calls = []

    async def handle_send_group(request):
        calls.append(
            {
                "headers": dict(request.headers),
                "json": await request.json(),
            }
        )
        return web.json_response({"status": "ok", "data": {"message_id": 42}})

    app = web.Application()
    app.router.add_post("/send_group_msg", handle_send_group)

    async with TestServer(app) as server:
        adapter = QQAdapter(
            PlatformConfig(
                enabled=True,
                extra={
                    "url": str(server.make_url("/")).rstrip("/"),
                    "access_token": "bridge-token",
                },
            )
        )

        result = await adapter.send("group:123456", "hello real bridge")

    assert result.success is True
    assert result.message_id == "42"
    assert calls[0]["json"]["group_id"] == 123456
    assert calls[0]["json"]["message"] == "hello real bridge"
    assert calls[0]["headers"]["Authorization"] == "Bearer bridge-token"


@pytest.mark.asyncio
async def test_send_does_not_allow_metadata_to_override_protected_fields():
    calls = []

    async def handle_send_group(request):
        calls.append(await request.json())
        return web.json_response({"status": "ok", "data": {"message_id": 99}})

    app = web.Application()
    app.router.add_post("/send_group_msg", handle_send_group)

    async with TestServer(app) as server:
        adapter = QQAdapter(
            PlatformConfig(
                enabled=True,
                extra={"url": str(server.make_url("/")).rstrip("/")},
            )
        )

        result = await adapter.send(
            "group:123456",
            "safe message",
            metadata={"group_id": 999999, "message": "tampered", "custom": "ok"},
        )

    assert result.success is True
    assert calls[0]["group_id"] == 123456
    assert calls[0]["message"] == "safe message"
    assert calls[0]["custom"] == "ok"


@pytest.mark.asyncio
async def test_connect_websocket_receives_and_forwards_message():
    async def handle_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 123456,
                "user_id": 24680,
                "message_id": 7,
                "message": [{"type": "text", "data": {"text": "hello from qq"}}],
                "sender": {"nickname": "qq-user"},
            }
        )
        await asyncio.sleep(0.05)
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/ws", handle_ws)

    async with TestServer(app) as server:
        ws_url = str(server.make_url("/ws")).replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        adapter = QQAdapter(PlatformConfig(enabled=True, extra={"url": ws_url}))
        adapter.handle_message = AsyncMock()

        ok = await adapter.connect()
        await asyncio.sleep(0.15)
        await adapter.disconnect()

    assert ok is True
    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.text == "hello from qq"
    assert event.source.chat_id == "group:123456"
    assert event.source.user_id == "24680"


@pytest.mark.asyncio
async def test_connect_websocket_drops_unauthorized_user_messages():
    async def handle_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 123456,
                "user_id": 99999,
                "message_id": 8,
                "message": [{"type": "text", "data": {"text": "blocked"}}],
                "sender": {"nickname": "blocked-user"},
            }
        )
        await asyncio.sleep(0.05)
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/ws", handle_ws)

    async with TestServer(app) as server:
        ws_url = str(server.make_url("/ws")).replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        adapter = QQAdapter(
            PlatformConfig(enabled=True, extra={"url": ws_url, "allowed_users": "24680"})
        )
        adapter.handle_message = AsyncMock()

        ok = await adapter.connect()
        await asyncio.sleep(0.15)
        await adapter.disconnect()

    assert ok is True
    adapter.handle_message.assert_not_awaited()
