"""MongoDB async client singleton (motor).

Falls back gracefully if motor is not installed or MongoDB is not reachable.
All public helpers return None / empty list / False when DB is unavailable.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("mastro.db")

_client = None
_db = None
_available: bool = False


# ---------------------------------------------------------------------------
# Init / teardown
# ---------------------------------------------------------------------------

def _load_mongo_cfg() -> dict:
    """Load mongodb.json from the config directory."""
    try:
        import json
        from ..paths import MONGODB_CONFIG_PATH
        if MONGODB_CONFIG_PATH.exists():
            with open(MONGODB_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


async def init_mongo() -> bool:
    """Attempt to connect to MongoDB. Returns True on success."""
    global _client, _db, _available
    cfg = _load_mongo_cfg()
    uri = cfg.get("uri", "")
    db_name = cfg.get("database", "mastro_agent")
    if not uri:
        logger.info("MongoDB: no URI configured, persistence disabled.")
        _available = False
        return False
    try:
        import motor.motor_asyncio  # type: ignore
        _client = motor.motor_asyncio.AsyncIOMotorClient(uri, serverSelectionTimeoutMS=4000)
        await _client.admin.command("ping")
        _db = _client[db_name]
        _available = True
        logger.info("MongoDB connected: %s / %s", uri, db_name)
        return True
    except ImportError:
        logger.warning("motor not installed — MongoDB persistence disabled. Run: pip install motor")
        _available = False
        return False
    except Exception as exc:
        logger.warning("MongoDB connection failed: %s", exc)
        _available = False
        _client = None
        _db = None
        return False


async def close_mongo() -> None:
    global _client, _db, _available
    if _client:
        _client.close()
    _client = None
    _db = None
    _available = False


def is_available() -> bool:
    return _available


# ---------------------------------------------------------------------------
# Test helper (called from config endpoint)
# ---------------------------------------------------------------------------

async def test_connection(uri: str, db_name: str) -> tuple[bool, str]:
    """Test a MongoDB URI without changing the global connection."""
    try:
        import motor.motor_asyncio
        client = motor.motor_asyncio.AsyncIOMotorClient(uri, serverSelectionTimeoutMS=4000)
        await client.admin.command("ping")
        client.close()
        return True, f"Connected to '{db_name}' successfully."
    except ImportError:
        return False, "motor not installed. Run: pip install motor"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

async def save_session(session: dict) -> bool:
    if not _available or _db is None:
        return False
    try:
        col = _db["chat_sessions"]
        await col.replace_one({"_id": session["_id"]}, session, upsert=True)
        return True
    except Exception as exc:
        logger.warning("save_session failed: %s", exc)
        return False


async def get_session(session_id: str) -> dict | None:
    if not _available or _db is None:
        return None
    try:
        col = _db["chat_sessions"]
        doc = await col.find_one({"_id": session_id})
        if doc:
            doc["id"] = doc.pop("_id")
        return doc
    except Exception as exc:
        logger.warning("get_session failed: %s", exc)
        return None


async def list_sessions(agent_id: str | None = None, limit: int = 50) -> list[dict]:
    if not _available or _db is None:
        return []
    try:
        col = _db["chat_sessions"]
        flt: dict[str, Any] = {}
        if agent_id:
            flt["agent_id"] = agent_id
        cursor = col.find(flt, {"messages": 0}).sort("updated_at", -1).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            results.append(doc)
        return results
    except Exception as exc:
        logger.warning("list_sessions failed: %s", exc)
        return []


async def delete_session(session_id: str) -> bool:
    if not _available or _db is None:
        return False
    try:
        col = _db["chat_sessions"]
        await col.delete_one({"_id": session_id})
        col2 = _db["reasoning_logs"]
        await col2.delete_many({"session_id": session_id})
        return True
    except Exception as exc:
        logger.warning("delete_session failed: %s", exc)
        return False


async def save_reasoning_log(log: dict) -> bool:
    if not _available or _db is None:
        return False
    try:
        col = _db["reasoning_logs"]
        await col.replace_one({"_id": log["_id"]}, log, upsert=True)
        return True
    except Exception as exc:
        logger.warning("save_reasoning_log failed: %s", exc)
        return False


async def get_reasoning_logs(session_id: str) -> list[dict]:
    if not _available or _db is None:
        return []
    try:
        col = _db["reasoning_logs"]
        cursor = col.find({"session_id": session_id}).sort("message_index", 1)
        results = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            results.append(doc)
        return results
    except Exception as exc:
        logger.warning("get_reasoning_logs failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

async def save_notification(notif: dict) -> bool:
    if not _available or _db is None:
        return False
    try:
        col = _db["notifications"]
        await col.replace_one({"_id": notif["_id"]}, notif, upsert=True)
        return True
    except Exception as exc:
        logger.warning("save_notification failed: %s", exc)
        return False


async def list_notifications(limit: int = 50, unread_only: bool = False) -> list[dict]:
    if not _available or _db is None:
        return []
    try:
        col = _db["notifications"]
        flt: dict[str, Any] = {"read": False} if unread_only else {}
        cursor = col.find(flt).sort("created_at", -1).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            results.append(doc)
        return results
    except Exception as exc:
        logger.warning("list_notifications failed: %s", exc)
        return []


async def mark_notification_read(notif_id: str) -> bool:
    if not _available or _db is None:
        return False
    try:
        await _db["notifications"].update_one({"_id": notif_id}, {"$set": {"read": True}})
        return True
    except Exception as exc:
        logger.warning("mark_notification_read failed: %s", exc)
        return False


async def mark_all_notifications_read() -> bool:
    if not _available or _db is None:
        return False
    try:
        await _db["notifications"].update_many({"read": False}, {"$set": {"read": True}})
        return True
    except Exception as exc:
        logger.warning("mark_all_notifications_read failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Tick history helpers (autonomous loop)
# ---------------------------------------------------------------------------

async def save_tick(tick: dict) -> bool:
    if not _available or _db is None:
        return False
    try:
        col = _db["tick_history"]
        await col.replace_one({"_id": tick["_id"]}, tick, upsert=True)
        return True
    except Exception as exc:
        logger.warning("save_tick failed: %s", exc)
        return False


async def list_ticks(agent_id: str, limit: int = 100) -> list[dict]:
    if not _available or _db is None:
        return []
    try:
        col = _db["tick_history"]
        cursor = col.find({"agent_id": agent_id}).sort("timestamp", -1).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            results.append(doc)
        return results
    except Exception as exc:
        logger.warning("list_ticks failed: %s", exc)
        return []


async def prune_ticks(agent_id: str, keep: int = 100) -> bool:
    """Keep only the most recent `keep` ticks for an agent, delete the rest."""
    if not _available or _db is None:
        return False
    try:
        col = _db["tick_history"]
        cursor = col.find({"agent_id": agent_id}, {"_id": 1}) \
                    .sort("timestamp", -1).skip(keep)
        old_ids = [doc["_id"] async for doc in cursor]
        if old_ids:
            await col.delete_many({"_id": {"$in": old_ids}})
        return True
    except Exception as exc:
        logger.warning("prune_ticks failed: %s", exc)
        return False


async def prune_reasoning_logs(session_id: str, keep: int = 100) -> bool:
    """Keep only the most recent `keep` reasoning logs of a session."""
    if not _available or _db is None:
        return False
    try:
        col = _db["reasoning_logs"]
        cursor = col.find({"session_id": session_id}, {"_id": 1}) \
                    .sort("created_at", -1).skip(keep)
        old_ids = [doc["_id"] async for doc in cursor]
        if old_ids:
            await col.delete_many({"_id": {"$in": old_ids}})
        return True
    except Exception as exc:
        logger.warning("prune_reasoning_logs failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Operational context helpers (context_entries)
# ---------------------------------------------------------------------------

async def save_context_entry(entry: dict) -> bool:
    if not _available or _db is None:
        return False
    try:
        col = _db["context_entries"]
        await col.replace_one({"_id": entry["_id"]}, entry, upsert=True)
        return True
    except Exception as exc:
        logger.warning("save_context_entry failed: %s", exc)
        return False


async def get_context_entry(entry_id: str) -> dict | None:
    if not _available or _db is None:
        return None
    try:
        return await _db["context_entries"].find_one({"_id": entry_id})
    except Exception as exc:
        logger.warning("get_context_entry failed: %s", exc)
        return None


async def list_context_entries(limit: int = 200) -> list[dict]:
    """All context entries, newest first. Entries are never hard-deleted."""
    if not _available or _db is None:
        return []
    try:
        col = _db["context_entries"]
        cursor = col.find({}).sort("created_at", -1).limit(limit)
        return [doc async for doc in cursor]
    except Exception as exc:
        logger.warning("list_context_entries failed: %s", exc)
        return []


async def update_context_entry(entry_id: str, fields: dict) -> bool:
    if not _available or _db is None:
        return False
    try:
        await _db["context_entries"].update_one({"_id": entry_id}, {"$set": fields})
        return True
    except Exception as exc:
        logger.warning("update_context_entry failed: %s", exc)
        return False


async def push_context_usage(entry_id: str, usage: dict, cap: int = 50) -> bool:
    """Append a usage record (capped) and bump the usage counters."""
    if not _available or _db is None:
        return False
    try:
        await _db["context_entries"].update_one(
            {"_id": entry_id},
            {
                "$push": {"usage": {"$each": [usage], "$slice": -cap}},
                "$inc": {"use_count": 1},
                "$set": {"last_used_at": usage.get("timestamp", now_iso())},
            },
        )
        return True
    except Exception as exc:
        logger.warning("push_context_usage failed: %s", exc)
        return False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
