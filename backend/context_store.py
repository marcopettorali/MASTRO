"""Operational Context Store — exogenous facts and goals for MASTRO agents.

Context entries describe facts, constraints or upcoming events that are NOT
observable through the agents' MCP monitoring tools: scheduled maintenance
windows, energy price forecasts, weather alerts, operator directives. They
are written by the operator (GUI / CLI) or by an external coordinator
(e.g. OpenClaw via the CLI) and injected deterministically into the system
prompt of every ReAct run — both INTENT chat turns and autonomous ticks —
by the prompt builder in mastro/react_engine.py. No LLM ever reads or writes
the store directly: producers write structured entries, the engine injects
their summaries, the agent reasons over them inside its single control loop.

Lifecycle (entries are never hard-deleted, the history stays inspectable):

    active ──(valid_until passes)──────────▶ expired   (derived at read time)
    active ──(one-shot injected in a run)──▶ consumed
    active ──(operator revokes)────────────▶ revoked
    active ◀──(enable/disable toggle)──────▶ disabled  (reversible, not a status)

Two injection semantics, defaulted per type and overridable per entry:
  - standing:  injected at every run while valid (maintenance windows,
               energy forecasts) — expires by time, not by use;
  - one_shot:  consumed by the first run that completes after injection
               (punctual directives).

Persistence follows the platform convention: MongoDB collection
'context_entries' when available, with a complete in-memory mirror as
fallback (same pattern as tick history in mastro/scheduler.py).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from .db import mongo

logger = logging.getLogger("mastro.context")

_MAX_MEM = 200        # cap for the in-memory mirror
USAGE_KEEP = 50       # usage records kept per entry
SUMMARY_MAX_LEN = 500
VALID_MODES = ("standing", "one_shot")

# Catalog of supported entry types. Closed set: the POST endpoint rejects
# anything else, so a misbehaving producer cannot inject arbitrary categories
# into the agents' prompts. Each type carries its default injection mode.
CONTEXT_TYPES: dict[str, dict] = {
    "maintenance":      {"mode": "standing", "label": "Scheduled maintenance"},
    "energy-forecast":  {"mode": "standing", "label": "Energy price / demand forecast"},
    "weather-alert":    {"mode": "standing", "label": "Weather alert"},
    "operational-note": {"mode": "standing", "label": "Operational note"},
    "directive":        {"mode": "one_shot", "label": "Operator directive"},
}

PROMPT_HEADER = (
    "---\n"
    "## Active Operational Context\n"
    "The following context entries were declared by the operator or by an "
    "external coordinator. They describe facts, constraints or upcoming "
    "events that are NOT visible through your monitoring tools. Take them "
    "into account in your reasoning and in every decision or recommendation "
    "you produce.\n"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def parse_iso(value) -> datetime | None:
    """Parse an ISO-8601 string; naive datetimes are assumed to be UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_time_valid(entry: dict, now: datetime) -> bool:
    vf = parse_iso(entry.get("valid_from"))
    vu = parse_iso(entry.get("valid_until"))
    if vf and now < vf:
        return False
    if vu and now >= vu:
        return False
    return True


def effective_status(entry: dict, now: datetime | None = None) -> str:
    """Status as shown to the operator. 'expired' and 'disabled' are derived:
    expiry is computed at read time (no TTL deletion), the enabled flag is a
    reversible toggle layered on top of the 'active' status."""
    now = now or _now()
    status = entry.get("status", "active")
    if status != "active":
        return status
    vu = parse_iso(entry.get("valid_until"))
    if vu and now >= vu:
        return "expired"
    if not entry.get("enabled", True):
        return "disabled"
    return "active"


def _public(entry: dict) -> dict:
    out = dict(entry)
    out["id"] = out.pop("_id")
    out["effective_status"] = effective_status(entry)
    return out


class ContextStore:
    def __init__(self) -> None:
        # Complete in-memory mirror (id -> entry), so the store keeps working
        # when MongoDB is unavailable; persistence across restarts requires it.
        self._mem: dict[str, dict] = {}

    # ── Creation ───────────────────────────────────────────────────────────

    async def add(
        self,
        *,
        type_: str,
        summary: str,
        source: str = "api",
        payload: dict | None = None,
        mode: str | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
    ) -> dict:
        entry = {
            "_id": uuid.uuid4().hex,
            "type": type_,
            "summary": summary.strip(),
            "payload": payload or {},
            "source": source.strip() or "api",
            "mode": mode or CONTEXT_TYPES[type_]["mode"],
            "created_at": _now_iso(),
            "valid_from": valid_from,
            "valid_until": valid_until,
            "status": "active",
            "enabled": True,
            "disabled_at": None,
            "disabled_by": None,
            "revoked_at": None,
            "revoked_by": None,
            "consumed_at": None,
            "consumed_by_session": None,
            "consumed_by_agent": None,
            "usage": [],
            "use_count": 0,
            "last_used_at": None,
        }
        await mongo.save_context_entry(dict(entry))
        self._mem_put(entry)
        logger.info("Context entry added [%s] from %s: %s",
                    entry["type"], entry["source"], entry["summary"][:80])
        return _public(entry)

    # ── Read ───────────────────────────────────────────────────────────────

    async def list(self, include_history: bool = True, limit: int = 200) -> list[dict]:
        """All entries, newest first. With include_history=False only entries
        whose effective status is 'active' or 'disabled' are returned."""
        entries = await mongo.list_context_entries(limit=limit)
        if not entries:
            entries = sorted(self._mem.values(),
                             key=lambda e: e.get("created_at", ""), reverse=True)[:limit]
        out = [_public(e) for e in entries]
        if not include_history:
            out = [e for e in out if e["effective_status"] in ("active", "disabled")]
        return out

    async def get_active(self) -> list[dict]:
        """Entries eligible for prompt injection: status 'active', enabled,
        and inside their validity window. Raw documents (with _id)."""
        now = _now()
        entries = await mongo.list_context_entries(limit=_MAX_MEM)
        if not entries:
            entries = list(self._mem.values())
        return [
            e for e in entries
            if e.get("status") == "active"
            and e.get("enabled", True)
            and _is_time_valid(e, now)
        ]

    # ── Prompt injection ───────────────────────────────────────────────────

    async def build_prompt_block(self) -> tuple[str, list[dict]]:
        """Format the active entries as a system-prompt block.

        Returns (block, entries): empty string and empty list when there is
        nothing to inject, so callers can skip the block entirely.
        """
        entries = await self.get_active()
        if not entries:
            return "", []
        lines = []
        for e in sorted(entries, key=lambda x: x.get("created_at", "")):
            validity = f", valid until {e['valid_until']}" if e.get("valid_until") else ""
            lines.append(f"- [{e['type']}] (source: {e['source']}{validity}): {e['summary']}")
        block = PROMPT_HEADER + "\n".join(lines) + "\n---"
        return block, entries

    async def record_usage(self, entries: list[dict], *, session_id: str, agent_id: str) -> None:
        """Record that a run completed with these entries injected.

        Called by the ReAct engine at the END of a successful run — never at
        injection time — so a run that fails midway leaves its one-shot
        entries active and they are re-proposed to the next run. Standing
        entries accumulate usage records; one-shot entries are additionally
        marked as consumed.
        """
        ts = _now_iso()
        usage = {"session_id": session_id, "agent_id": agent_id, "timestamp": ts}
        for e in entries:
            entry_id = e["_id"]
            await mongo.push_context_usage(entry_id, dict(usage), cap=USAGE_KEEP)
            mem = self._mem.get(entry_id)
            if mem is not None:
                mem.setdefault("usage", []).append(dict(usage))
                del mem["usage"][:-USAGE_KEEP]
                mem["use_count"] = mem.get("use_count", 0) + 1
                mem["last_used_at"] = ts
            if e.get("mode") == "one_shot" and e.get("status") == "active":
                fields = {
                    "status": "consumed",
                    "consumed_at": ts,
                    "consumed_by_session": session_id,
                    "consumed_by_agent": agent_id,
                }
                await mongo.update_context_entry(entry_id, fields)
                if mem is not None:
                    mem.update(fields)

    # ── Operator actions (all reversible or soft — no hard delete) ─────────

    async def set_enabled(self, entry_id: str, enabled: bool, by: str = "gui") -> dict | None:
        entry = await self._fetch(entry_id)
        if not entry:
            return None
        fields = {
            "enabled": enabled,
            "disabled_at": None if enabled else _now_iso(),
            "disabled_by": None if enabled else by,
        }
        await mongo.update_context_entry(entry_id, fields)
        entry.update(fields)
        self._mem_put(entry)
        return _public(entry)

    async def revoke(self, entry_id: str, by: str = "gui") -> dict | None:
        entry = await self._fetch(entry_id)
        if not entry:
            return None
        if entry.get("status") == "active":
            fields = {"status": "revoked", "revoked_at": _now_iso(), "revoked_by": by}
            await mongo.update_context_entry(entry_id, fields)
            entry.update(fields)
            self._mem_put(entry)
        return _public(entry)

    # ── Internals ──────────────────────────────────────────────────────────

    async def _fetch(self, entry_id: str) -> dict | None:
        entry = await mongo.get_context_entry(entry_id)
        if entry:
            return entry
        mem = self._mem.get(entry_id)
        return dict(mem) if mem else None

    def _mem_put(self, entry: dict) -> None:
        self._mem[entry["_id"]] = dict(entry)
        if len(self._mem) > _MAX_MEM:
            # Evict oldest non-active entries first, then oldest overall.
            candidates = sorted(
                self._mem.values(),
                key=lambda e: (e.get("status") == "active", e.get("created_at", "")),
            )
            for victim in candidates[: len(self._mem) - _MAX_MEM]:
                self._mem.pop(victim["_id"], None)


# Module-level singleton, imported by the router and the ReAct engine.
context_store = ContextStore()
