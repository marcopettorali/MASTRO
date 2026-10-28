"""Notification Service — operator notifications for autonomous agents.

Channels:
  - In-app: persisted to MongoDB (collection 'notifications', in-memory
    fallback) and broadcast to the GUI via SSE (/api/notifications/stream).
  - Optional webhook (ntfy-compatible): real push notifications to the
    operator's devices. Configured in config/notifications.json:
        {"webhook_url": "https://ntfy.sh/<topic>"}
    Leave empty to disable.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

from .db import mongo
from .paths import NOTIFICATIONS_CONFIG_PATH

logger = logging.getLogger("mastro.notifications")

_MAX_MEM = 200  # cap for the in-memory fallback store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_webhook_url() -> str:
    try:
        if NOTIFICATIONS_CONFIG_PATH.exists():
            cfg = json.loads(NOTIFICATIONS_CONFIG_PATH.read_text(encoding="utf-8"))
            return (cfg.get("webhook_url") or "").strip()
    except Exception:
        pass
    return ""


async def test_webhook(url: str) -> tuple[bool, str]:
    """Send a test push to an ntfy-compatible webhook without saving config."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                content="Test notification from MASTRO.".encode("utf-8"),
                headers={"Title": "MASTRO test", "Priority": "default", "Tags": "white_check_mark"},
            )
            if resp.status_code < 300:
                return True, f"Test notification sent (HTTP {resp.status_code})."
            return False, f"Webhook responded with HTTP {resp.status_code}."
    except Exception as exc:
        return False, str(exc)


class NotificationService:
    def __init__(self) -> None:
        self._mem: list[dict] = []                  # in-memory fallback
        self._subscribers: set[asyncio.Queue] = set()

    # ── Creation ───────────────────────────────────────────────────────────

    async def notify(
        self,
        *,
        agent_id: str,
        session_id: str | None,
        severity: str,
        title: str,
        message: str,
    ) -> dict:
        notif = {
            "_id": uuid.uuid4().hex,
            "agent_id": agent_id,
            "session_id": session_id,
            "severity": severity,
            "title": title,
            "message": message,
            "created_at": _now(),
            "read": False,
        }
        saved = await mongo.save_notification(dict(notif))
        if not saved:
            self._mem.append(dict(notif))
            del self._mem[:-_MAX_MEM]

        public = dict(notif)
        public["id"] = public.pop("_id")
        self._broadcast(public)

        webhook_url = _load_webhook_url()
        if webhook_url:
            await self._push_webhook(webhook_url, public)

        logger.info("Notification [%s] %s", severity, title)
        return public

    def _broadcast(self, notif: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(notif)
            except Exception:
                self._subscribers.discard(q)

    async def _push_webhook(self, url: str, notif: dict) -> None:
        """POST in ntfy-compatible format (plain body + headers)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    url,
                    content=notif["message"].encode("utf-8"),
                    headers={
                        "Title": notif["title"],
                        "Priority": "urgent" if notif["severity"] == "critical" else "high",
                        "Tags": "rotating_light" if notif["severity"] == "critical" else "warning",
                    },
                )
        except Exception as exc:
            logger.warning("Webhook push failed: %s", exc)

    # ── Read / update ──────────────────────────────────────────────────────

    async def list(self, limit: int = 50, unread_only: bool = False) -> list[dict]:
        items = await mongo.list_notifications(limit=limit, unread_only=unread_only)
        if items:
            return items
        out = []
        for n in self._mem:
            if unread_only and n.get("read"):
                continue
            d = dict(n)
            d["id"] = d.pop("_id")
            out.append(d)
        out.sort(key=lambda n: n.get("created_at", ""), reverse=True)
        return out[:limit]

    async def mark_read(self, notif_id: str) -> None:
        await mongo.mark_notification_read(notif_id)
        for n in self._mem:
            if n["_id"] == notif_id:
                n["read"] = True

    async def mark_all_read(self) -> None:
        await mongo.mark_all_notifications_read()
        for n in self._mem:
            n["read"] = True

    # ── SSE stream ─────────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)


# Module-level singleton, imported by routers and the scheduler
notifier = NotificationService()
