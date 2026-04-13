"""
QQ platform adapter via a local OneBot-compatible bridge.

This adapter targets Windows-native deployments where Hermes connects to
NapCat / LLOneBot / similar OneBot bridges over HTTP or WebSocket.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterable
from typing import Any, Dict, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)


def check_qq_requirements(config: PlatformConfig | None = None) -> bool:
    if aiohttp is None:
        return False
    if config is not None:
        return bool((config.extra or {}).get("url"))
    return bool(
        os.getenv("QQ_ONEBOT_URL")
        or os.getenv("QQ_ONEBOT_WS_URL")
        or os.getenv("QQ_ONEBOT_HTTP_URL")
    )


class QQAdapter(BasePlatformAdapter):
    """Minimal QQ adapter for OneBot-compatible bridges."""

    MAX_MESSAGE_LENGTH = 4000

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.QQ)
        self._url = str((config.extra or {}).get("url", "")).strip()
        self._access_token = str((config.extra or {}).get("access_token", "")).strip()
        self._default_target_type = str((config.extra or {}).get("default_target_type", "group")).strip().lower() or "group"
        self._allowed_user_ids = self._load_allowed_user_ids(config)
        self._session: aiohttp.ClientSession | None = None
        self._ws_task: asyncio.Task | None = None

    async def connect(self) -> bool:
        if aiohttp is None:
            self.set_fatal_error("qq_missing_dependency", "aiohttp is required for QQ bridge support.", retryable=False)
            return False
        if not self._url:
            self.set_fatal_error("qq_missing_url", "QQ_ONEBOT_URL is not configured.", retryable=False)
            return False

        self._running = True
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))

        if self._url.startswith(("ws://", "wss://")):
            try:
                headers = self._auth_headers()
                ws = await self._session.ws_connect(self._url, heartbeat=30, headers=headers)
            except Exception as exc:
                self.set_fatal_error("qq_connect_failed", f"QQ bridge connection failed: {exc}", retryable=True)
                await self.disconnect()
                return False
            self._ws_task = asyncio.create_task(self._listen(ws))

        return True

    async def disconnect(self) -> None:
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._ws_task = None
        if self._session:
            await self._session.close()
            self._session = None

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if aiohttp is None:
            return SendResult(success=False, error="aiohttp is required for QQ bridge support.")

        target_type, target_id = self._parse_chat_target(chat_id)
        if not target_id:
            return SendResult(success=False, error=f"Invalid QQ chat target: {chat_id}")

        api_url = self._resolve_http_api_url()
        if not api_url:
            return SendResult(success=False, error="QQ bridge HTTP endpoint could not be resolved from QQ_ONEBOT_URL.")

        payload: dict[str, Any] = {"message": self.format_message(content)}
        if target_type == "group":
            action = "send_group_msg"
            payload["group_id"] = int(target_id) if target_id.isdigit() else target_id
        else:
            action = "send_private_msg"
            payload["user_id"] = int(target_id) if target_id.isdigit() else target_id

        if reply_to:
            payload["reply"] = {"id": reply_to}
        if metadata:
            protected_keys = {"message", "group_id", "user_id", "reply"}
            for key, value in metadata.items():
                if key in protected_keys:
                    logger.warning("[QQ] Ignoring metadata override for protected field: %s", key)
                    continue
                payload[key] = value

        session = self._session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        created_session = session is not self._session
        try:
            async with session.post(
                f"{api_url}/{action}",
                json=payload,
                headers=self._auth_headers(),
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    return SendResult(success=False, error=f"QQ bridge HTTP {resp.status}: {data}")
                if data.get("status") not in (None, "ok"):
                    return SendResult(success=False, error=f"QQ bridge send failed: {data}")
                message_id = None
                if isinstance(data.get("data"), dict):
                    message_id = data["data"].get("message_id")
                return SendResult(success=True, message_id=str(message_id) if message_id is not None else None, raw_response=data)
        except Exception as exc:
            return SendResult(success=False, error=f"QQ send failed: {exc}", retryable=True)
        finally:
            if created_session:
                await session.close()

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        target_type, target_id = self._parse_chat_target(chat_id)
        if target_type == "group":
            return {"name": f"QQ Group {target_id}", "type": "group", "chat_id": f"group:{target_id}"}
        return {"name": f"QQ User {target_id}", "type": "dm", "chat_id": f"user:{target_id}"}

    def format_message(self, content: str) -> str:
        return content

    def _auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            return {}
        return {"Authorization": f"Bearer {self._access_token}"}

    def _resolve_http_api_url(self) -> str:
        if self._url.startswith(("http://", "https://")):
            return self._url.rstrip("/")
        if self._url.startswith("ws://"):
            return "http://" + self._url[len("ws://"):].rstrip("/")
        if self._url.startswith("wss://"):
            return "https://" + self._url[len("wss://"):].rstrip("/")
        return self._url.rstrip("/")

    def _parse_chat_target(self, chat_id: str) -> tuple[str, str]:
        raw = str(chat_id or "").strip()
        if ":" in raw:
            prefix, rest = raw.split(":", 1)
            prefix = prefix.lower().strip()
            if prefix in {"group", "user", "private"}:
                return ("group" if prefix == "group" else "user", rest.strip())
        if self._default_target_type == "user":
            return "user", raw
        return "group", raw

    async def _listen(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    payload = msg.json()
                except Exception:
                    continue
                await self._handle_payload(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._running:
                self.set_fatal_error("qq_listener_failed", f"QQ bridge listener failed: {exc}", retryable=True)
        finally:
            await ws.close()

    async def _handle_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("post_type") != "message":
            return

        message_type = str(payload.get("message_type", "")).lower()
        user_id = str(payload.get("user_id", "")).strip() or None
        sender = payload.get("sender") or {}
        user_name = sender.get("nickname") or sender.get("card") or sender.get("remark") or user_id

        if not self._is_allowed_user(user_id):
            logger.info("[QQ] Ignoring message from unauthorized user: %s", user_id or "<unknown>")
            return

        if message_type == "group":
            group_id = str(payload.get("group_id", "")).strip()
            source = self.build_source(
                chat_id=f"group:{group_id}",
                chat_name=str(payload.get("group_name") or f"QQ Group {group_id}"),
                chat_type="group",
                user_id=user_id,
                user_name=user_name,
            )
        else:
            source = self.build_source(
                chat_id=f"user:{user_id}",
                chat_name=user_name,
                chat_type="dm",
                user_id=user_id,
                user_name=user_name,
            )

        text = self._extract_text(payload.get("raw_message", payload.get("message", "")))
        if not text.strip():
            return

        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=payload,
            message_id=str(payload.get("message_id", "")) or None,
        )
        await self.handle_message(event)

    @staticmethod
    def _extract_text(message: Any) -> str:
        if isinstance(message, str):
            return message.strip()
        if isinstance(message, list):
            parts: list[str] = []
            for item in message:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    parts.append(str((item.get("data") or {}).get("text", "")))
            return "".join(parts).strip()
        return str(message or "").strip()

    @staticmethod
    def _normalize_allowed_values(values: Iterable[Any]) -> set[str]:
        normalized: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if text:
                normalized.add(text)
        return normalized

    def _load_allowed_user_ids(self, config: PlatformConfig) -> set[str]:
        extra = config.extra or {}
        configured = extra.get("allowed_users")
        if isinstance(configured, str):
            values = configured.split(",")
        elif isinstance(configured, Iterable):
            values = configured
        else:
            values = os.getenv("QQ_ALLOWED_USERS", "").split(",")
        return self._normalize_allowed_values(values)

    def _is_allowed_user(self, user_id: str | None) -> bool:
        if not self._allowed_user_ids or "*" in self._allowed_user_ids:
            return True
        return bool(user_id and user_id in self._allowed_user_ids)
