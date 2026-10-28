"""Agent Scheduler — autonomous sampling loop for MASTRO agents.

Each agent whose config contains an "autonomous" block with enabled=true is
run periodically: at every tick the ReAct loop analyses the system state via
the agent's MCP tools and must conclude with a structured verdict:

    {"status": "ok" | "warning" | "critical",
     "summary": "<one sentence>", "details": "<optional>"}

If the verdict status matches the agent's notify_on list, an operator
notification is emitted through the NotificationService.

Sessions are persisted exactly like chat sessions (MongoDB collection
'chat_sessions', in-memory fallback) with session_type="autonomous",
so they are inspectable from the Chat page like any other session.

Agent config block (inside config/agents.json):

    "autonomous": {
        "enabled": true,
        "interval_seconds": 300,
        "task_prompt": "Analyse the current system state ...",
        "notify_on": ["warning", "critical"]
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from ..paths import AGENTS_CONFIG_PATH, LLM_SETTINGS_PATH, SKILLS_DIR
from ..db import mongo
from . import react_engine

logger = logging.getLogger("mastro.scheduler")

MIN_INTERVAL_SECONDS = 5
FIRST_TICK_DELAY_SECONDS = 1   # short initial delay before an agent's very first tick
                               # (catch a fast-developing condition early) then `interval`
MAX_STORED_MESSAGES = 40   # cap autonomous session growth
TICK_HISTORY_KEEP = 100    # keep the last N tick records per agent

VERDICT_PATTERN = re.compile(r"\{[^{}]*\"status\"[^{}]*\}", re.DOTALL)

VERDICT_INSTRUCTIONS = (
    "\n\nAt the end of your analysis you MUST conclude your answer with a "
    "single JSON block in this exact format:\n"
    '{"status": "ok" | "warning" | "critical", '
    '"summary": "<one sentence>", "details": "<optional details>"}\n'
    'Use "warning" for conditions worth monitoring and "critical" for '
    "conditions that require operator intervention."
)

DEFAULT_TASK_PROMPT = (
    "Analyse the current state of the managed infrastructure: node status, metrics "
    "and job activity. Identify anomalies or conditions that deserve the "
    "operator's attention."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_verdict(text: str) -> dict:
    """Extract the last JSON block containing a valid 'status' field."""
    matches = VERDICT_PATTERN.findall(text or "")
    for raw in reversed(matches):
        try:
            v = json.loads(raw)
            if v.get("status") in ("ok", "warning", "critical"):
                return {
                    "status": v["status"],
                    "summary": str(v.get("summary", "")).strip(),
                    "details": str(v.get("details", "")).strip(),
                }
        except json.JSONDecodeError:
            continue
    return {
        "status": "unknown",
        "summary": "Verdict not parsable from agent answer",
        "details": (text or "")[-500:],
    }


def _load_agents() -> list[dict]:
    if not AGENTS_CONFIG_PATH.exists():
        return []
    try:
        return json.loads(AGENTS_CONFIG_PATH.read_text(encoding="utf-8")).get("agents", [])
    except Exception:
        return []


def _load_llm_settings() -> dict:
    if not LLM_SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(LLM_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


class AgentScheduler:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._running_tick: set[str] = set()
        self._sessions: dict[str, dict] = {}      # agent_id -> session doc
        self._status: dict[str, dict] = {}        # agent_id -> last tick info
        self._tick_history: dict[str, list[dict]] = {}  # in-memory fallback
        self._started = False

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._started = True
        await self.reload()
        logger.info("AgentScheduler started")

    async def stop(self) -> None:
        self._started = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    async def reload(self) -> None:
        """Restart the loops from the current agent configuration.

        Called at startup and after every agent create/update/delete.
        """
        if not self._started:
            return
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        for agent in _load_agents():
            cfg = agent.get("autonomous") or {}
            if cfg.get("enabled"):
                agent_id = agent["id"]
                self._tasks[agent_id] = asyncio.create_task(
                    self._loop(agent_id), name=f"agent-loop-{agent_id}"
                )
                logger.info(
                    "Autonomous loop active for %s every %ss",
                    agent_id, cfg.get("interval_seconds", 300),
                )

    # ── Loop ───────────────────────────────────────────────────────────────

    async def _loop(self, agent_id: str) -> None:
        first = True
        while True:
            agent = self._find(agent_id)
            if not agent or not (agent.get("autonomous") or {}).get("enabled"):
                return
            interval = max(
                MIN_INTERVAL_SECONDS,
                int((agent.get("autonomous") or {}).get("interval_seconds", 300)),
            )
            # Sleep BEFORE each sampling so an agent enabled at t0 does not fire on stale
            # startup state. The FIRST sampling uses a short delay (FIRST_TICK_DELAY) so a
            # fast-developing condition is caught early; subsequent samplings use `interval`.
            await asyncio.sleep(min(FIRST_TICK_DELAY_SECONDS, interval) if first else interval)
            first = False
            agent = self._find(agent_id)
            if not agent or not (agent.get("autonomous") or {}).get("enabled"):
                return
            try:
                await self.tick(agent_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Tick failed for %s", agent_id)

    async def tick(self, agent_id: str, trigger: str = "scheduled") -> dict:
        """Run a single autonomous sampling. Also used for manual triggering."""
        if agent_id in self._running_tick:
            logger.warning("Tick skipped for %s: previous tick still running", agent_id)
            return {"skipped": True, "reason": "previous tick still running"}

        agent = self._find(agent_id)
        if not agent:
            raise ValueError(f"Agent '{agent_id}' not found")

        cfg = agent.get("autonomous") or {}
        task_prompt = (cfg.get("task_prompt") or DEFAULT_TASK_PROMPT).strip()
        message = task_prompt + VERDICT_INSTRUCTIONS

        mcp_servers = agent.get("mcp_servers") or []
        mcp_url = mcp_servers[0]["url"] if mcp_servers else "http://localhost:8001/mcp"
        llm_settings = agent.get("llm_override") or _load_llm_settings()

        session = self._get_or_create_session(agent)
        history = session.get("messages", [])

        self._running_tick.add(agent_id)
        started_at = _now()
        t0 = asyncio.get_event_loop().time()
        try:
            final_answer, reasoning_steps, context_ids = await self._run_turn(
                session_id=session["_id"],
                agent=agent,
                history=history,
                message=message,
                llm_settings=llm_settings,
                mcp_url=mcp_url,
            )
        finally:
            self._running_tick.discard(agent_id)
        duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)

        verdict = parse_verdict(final_answer)
        verdict.update({
            "agent_id": agent_id,
            "session_id": session["_id"],
            "timestamp": started_at,
        })

        # ── Persist session (same shape and storage as chat sessions) ──────
        session["messages"] = (history + [
            {"role": "user", "content": message, "timestamp": started_at},
            {
                "role": "assistant",
                "content": final_answer,
                "timestamp": _now(),
                "reasoning_steps": reasoning_steps,
            },
        ])[-MAX_STORED_MESSAGES:]
        session["updated_at"] = _now()
        session["last_verdict"] = verdict
        await self._persist_session(session)

        if reasoning_steps:
            await mongo.save_reasoning_log({
                "_id": str(uuid.uuid4()),
                "session_id": session["_id"],
                "message_index": len(session["messages"]) // 2,
                "steps": reasoning_steps,
                "final_answer": final_answer,
                "context_ids": context_ids,
                "created_at": _now(),
            })

        # ── Record tick in history (last TICK_HISTORY_KEEP per agent) ──────
        tick_record = {
            "_id": uuid.uuid4().hex,
            "agent_id": agent_id,
            "agent_name": agent.get("name", agent_id),
            "session_id": session["_id"],
            "timestamp": started_at,
            "duration_ms": duration_ms,
            "trigger": trigger,
            "status": verdict["status"],
            "summary": verdict.get("summary", ""),
            "details": verdict.get("details", ""),
            "answer": final_answer,
            "context_ids": context_ids,
        }
        await self._record_tick(tick_record)
        await mongo.prune_reasoning_logs(session["_id"], keep=TICK_HISTORY_KEEP)

        self._status[agent_id] = {
            "last_tick_at": started_at,
            "last_verdict": verdict,
            "session_id": session["_id"],
        }

        # ── Notify operator if needed ───────────────────────────────────────
        notify_on = cfg.get("notify_on") or ["warning", "critical"]
        if verdict["status"] in notify_on:
            from ..notifications import notifier
            await notifier.notify(
                agent_id=agent_id,
                session_id=session["_id"],
                severity=verdict["status"],
                title=f"[{agent.get('name', agent_id)}] {verdict['status'].upper()}",
                message=verdict.get("summary") or "Condition detected, see session for details.",
            )

        return verdict

    # ── Internals ──────────────────────────────────────────────────────────

    async def _run_turn(
        self, *, session_id: str, agent: dict, history: list[dict],
        message: str, llm_settings: dict, mcp_url: str,
    ) -> tuple[str, list[dict], list[str]]:
        """Consume the ReAct SSE generator and collect the final answer."""
        tokens: list[str] = []
        reasoning_steps: list[dict] = []
        context_ids: list[str] = []
        error: str | None = None

        gen: AsyncGenerator[str, None] = react_engine.run(
            session_id=session_id,
            agent_config=agent,
            conversation_history=history,
            user_message=message,
            llm_settings=llm_settings,
            mcp_url=mcp_url,
            skills_dir=SKILLS_DIR,
        )
        async for chunk in gen:
            try:
                evt = json.loads(chunk.removeprefix("data:").strip())
            except Exception:
                continue
            etype = evt.get("type")
            if etype == "token":
                tokens.append(evt.get("content", ""))
            elif etype == "done":
                reasoning_steps = evt.get("reasoning_steps", [])
                context_ids = evt.get("context_ids", [])
            elif etype == "error":
                error = evt.get("message", "unknown error")

        final_answer = "".join(tokens).strip()
        if error and not final_answer:
            final_answer = f"(Engine error: {error})"
        return final_answer, reasoning_steps, context_ids

    def reset_session(self, agent_id: str) -> dict:
        """Drop the agent's in-memory autonomous session (conversation context + tick
        history) so the NEXT tick starts from a clean slate. Used between independent
        experiment runs: the scheduler otherwise reuses one session per agent for the whole
        backend lifetime, so an agent's context accumulates across runs (up to
        MAX_STORED_MESSAGES) and it starts answering "already migrated / no action needed"
        from a PRIOR run's history even though the cluster was reset — silently biasing every
        run after the first. Clearing here forces a fresh session_id + empty history next tick.
        Chat/UI sessions are unaffected (they live in the intent store, not here)."""
        had = self._sessions.pop(agent_id, None) is not None
        self._tick_history.pop(agent_id, None)
        self._status.pop(agent_id, None)
        return {"ok": True, "agent_id": agent_id, "cleared": had}

    def _get_or_create_session(self, agent: dict) -> dict:
        agent_id = agent["id"]
        session = self._sessions.get(agent_id)
        if session is None:
            session = {
                "_id": f"auto-{agent_id}-{uuid.uuid4().hex[:8]}",
                "agent_id": agent_id,
                "agent_name": agent.get("name", agent_id),
                "session_type": "autonomous",
                "created_at": _now(),
                "updated_at": _now(),
                "messages": [],
                "status": "active",
            }
            self._sessions[agent_id] = session
        return session

    async def _persist_session(self, session: dict) -> None:
        # Mirror into the INTENT in-memory store so the session is visible
        # from the Chat page even when MongoDB is unavailable.
        try:
            from ..routers import intent as intent_router
            intent_router._mem_save(session)
        except Exception:
            pass
        await mongo.save_session(session)

    async def _record_tick(self, tick: dict) -> None:
        """Persist a tick record and enforce the retention policy."""
        saved = await mongo.save_tick(dict(tick))
        if saved:
            await mongo.prune_ticks(tick["agent_id"], keep=TICK_HISTORY_KEEP)
        # Always mirror in memory so history is available when MongoDB is off
        bucket = self._tick_history.setdefault(tick["agent_id"], [])
        public = dict(tick)
        public["id"] = public.pop("_id")
        bucket.append(public)
        del bucket[:-TICK_HISTORY_KEEP]

    async def history(self, agent_id: str, limit: int = TICK_HISTORY_KEEP) -> list[dict]:
        """Tick history for an agent, newest first."""
        items = await mongo.list_ticks(agent_id, limit=min(limit, TICK_HISTORY_KEEP))
        if items:
            return items
        bucket = self._tick_history.get(agent_id, [])
        return list(reversed(bucket))[:limit]

    def _find(self, agent_id: str) -> dict | None:
        return next((a for a in _load_agents() if a.get("id") == agent_id), None)

    # ── Introspection ──────────────────────────────────────────────────────

    def status(self) -> list[dict]:
        out = []
        for agent in _load_agents():
            cfg = agent.get("autonomous") or {}
            if not cfg:
                continue
            agent_id = agent["id"]
            info = {
                "agent_id": agent_id,
                "agent_name": agent.get("name", agent_id),
                "enabled": bool(cfg.get("enabled")),
                "interval_seconds": cfg.get("interval_seconds", 300),
                "loop_active": agent_id in self._tasks
                               and not self._tasks[agent_id].done(),
                "tick_running": agent_id in self._running_tick,
            }
            info.update(self._status.get(agent_id, {}))
            out.append(info)
        return out


# Module-level singleton, imported by routers and gui_backend
scheduler = AgentScheduler()
