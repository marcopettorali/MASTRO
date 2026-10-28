"""Autonomous Module — operator notifications and autonomous loop endpoints."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..notifications import notifier, test_webhook
from ..agent.scheduler import scheduler
from ..paths import NOTIFICATIONS_CONFIG_PATH

router = APIRouter()
logger = logging.getLogger("mastro.autonomous")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/api/notifications")
async def list_notifications(limit: int = 50, unread_only: bool = False):
    items = await notifier.list(limit=limit, unread_only=unread_only)
    return {"ok": True, "notifications": items}


@router.post("/api/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str):
    await notifier.mark_read(notif_id)
    return {"ok": True}


@router.post("/api/notifications/read-all")
async def mark_all_notifications_read():
    await notifier.mark_all_read()
    return {"ok": True}


@router.get("/api/notifications/stream")
async def notifications_stream():
    """SSE stream: pushes each new notification to the GUI in real time."""
    queue = notifier.subscribe()

    async def event_stream():
        try:
            while True:
                try:
                    notif = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {json.dumps(notif, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # keep-alive comment so proxies don't drop the connection
                    yield ": keep-alive\n\n"
        finally:
            notifier.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Autonomous loop
# ---------------------------------------------------------------------------

@router.get("/api/autonomous/status")
async def autonomous_status():
    return {"ok": True, "agents": scheduler.status()}


@router.post("/api/autonomous/{agent_id}/tick")
async def manual_tick(agent_id: str):
    """Trigger a single sampling manually (testing / evaluation)."""
    try:
        verdict = await scheduler.tick(agent_id, trigger="manual")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "verdict": verdict}


@router.get("/api/autonomous/{agent_id}/history")
async def tick_history(agent_id: str, limit: int = 100):
    """Tick history (last 100 per agent), newest first."""
    ticks = await scheduler.history(agent_id, limit=limit)
    return {"ok": True, "ticks": ticks}


@router.post("/api/autonomous/{agent_id}/reset-session")
async def reset_autonomous_session(agent_id: str):
    """Drop the agent's in-memory autonomous session so the next tick starts clean.
    Used between independent experiment runs to prevent conversation carryover across runs."""
    return scheduler.reset_session(agent_id)


# ---------------------------------------------------------------------------
# Notifications webhook config
# ---------------------------------------------------------------------------

def _load_notif_cfg() -> dict:
    if not NOTIFICATIONS_CONFIG_PATH.exists():
        return {"webhook_url": ""}
    try:
        return json.loads(NOTIFICATIONS_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"webhook_url": ""}


@router.get("/api/config/notifications")
async def get_notifications_config():
    return {"ok": True, "config": _load_notif_cfg()}


@router.post("/api/config/notifications")
async def save_notifications_config(payload: dict):
    cfg = payload.get("config", payload)
    out = {"webhook_url": (cfg.get("webhook_url") or "").strip()}
    NOTIFICATIONS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTIFICATIONS_CONFIG_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": True}


@router.post("/api/config/notifications/test")
async def test_notifications_webhook(payload: dict):
    url = (payload.get("webhook_url") or "").strip()
    if not url:
        return {"ok": False, "message": "Webhook URL is required"}
    ok, msg = await test_webhook(url)
    return {"ok": ok, "message": msg}
