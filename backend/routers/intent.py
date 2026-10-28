"""INTENT Module — Chat API with decoupled ReAct execution and SSE streaming.

The ReAct turn runs in a detached background task (see agent.run_manager) so it
completes and persists to MongoDB regardless of whether the operator stays on the
page. The SSE endpoints only *observe* a run; a client disconnecting (closing the
tab, navigating away, aborting the fetch) never interrupts the run.

Endpoints:
  POST   /api/intent/chat              start a run, return an SSE stream that observes it
  GET    /api/intent/stream/{run_id}   reconnect to an in-flight / recent run (replay + live)
  GET    /api/intent/active            active run for a session, if any (for re-entry)
  GET    /api/intent/sessions          list sessions
  GET    /api/intent/sessions/{id}     load a session (+ reasoning logs)
  DELETE /api/intent/sessions/{id}     delete a session
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..paths import AGENTS_CONFIG_PATH, LLM_SETTINGS_PATH, SKILLS_DIR
from ..db import mongo
from ..agent import react_engine
from ..agent.run_manager import run_manager, RunState

router = APIRouter()
logger = logging.getLogger("mastro.intent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_agents() -> list[dict]:
    if not AGENTS_CONFIG_PATH.exists():
        return []
    try:
        data = json.loads(AGENTS_CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("agents", [])
    except Exception:
        return []


def _load_llm_settings() -> dict:
    if not LLM_SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(LLM_SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_agent(agent_id: str) -> dict | None:
    for a in _load_agents():
        if a.get("id") == agent_id:
            return a
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# In-memory session store (fallback when MongoDB is unavailable)
_mem_sessions: dict[str, dict] = {}


def _mem_save(session: dict) -> None:
    _mem_sessions[session["_id"]] = session


def _mem_get(session_id: str) -> dict | None:
    doc = _mem_sessions.get(session_id)
    if doc:
        out = dict(doc)
        out["id"] = out.pop("_id", session_id)
        return out
    return None


def _mem_list(agent_id: str | None) -> list[dict]:
    items = []
    for doc in _mem_sessions.values():
        if agent_id and doc.get("agent_id") != agent_id:
            continue
        out = {k: v for k, v in doc.items() if k != "messages"}
        out["id"] = out.pop("_id", out.get("id", ""))
        items.append(out)
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items[:50]


# ---------------------------------------------------------------------------
# Detached run executor — independent of any client connection
# ---------------------------------------------------------------------------

async def _execute_run(
    run: RunState,
    *,
    agent: dict,
    conversation_history: list[dict],
    user_message: str,
    llm_settings: dict,
    mcp_url: str,
    session: dict,
    session_id: str,
) -> None:
    """Run one ReAct turn to completion, publishing SSE chunks, then persist.

    Runs as a background asyncio task: it does NOT depend on a client being
    connected, so the turn always finishes and is saved even if the operator
    leaves the page.
    """
    collected_tokens: list[str] = []
    reasoning_steps: list[dict] = []
    context_ids: list[str] = []
    status = "done"

    try:
        async for chunk in react_engine.run(
            session_id=session_id,
            agent_config=agent,
            conversation_history=conversation_history,
            user_message=user_message,
            llm_settings=llm_settings,
            mcp_url=mcp_url,
            skills_dir=SKILLS_DIR,
        ):
            await run.publish(chunk)
            # Parse to collect final data for persistence
            try:
                evt = json.loads(chunk.removeprefix("data:").strip())
                if evt["type"] == "token":
                    collected_tokens.append(evt.get("content", ""))
                elif evt["type"] == "done":
                    reasoning_steps = evt.get("reasoning_steps", [])
                    context_ids = evt.get("context_ids", [])
            except Exception:
                pass
    except asyncio.CancelledError:
        # Server shutting down — do not persist a partial turn.
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("intent run %s failed: %s", run.run_id, exc)
        status = "error"
        await run.publish(
            "data: "
            + json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            + "\n\n"
        )

    # ── Persist regardless of client presence ──────────────────────────────
    try:
        final_answer = "".join(collected_tokens)
        session["messages"] = conversation_history + [
            {"role": "user", "content": user_message, "timestamp": _now()},
            {
                "role": "assistant",
                "content": final_answer,
                "timestamp": _now(),
                "reasoning_steps": reasoning_steps,
            },
        ]
        session["updated_at"] = _now()
        session["_id"] = session_id

        _mem_save(session)
        await mongo.save_session(session)

        # Save reasoning log separately for inspection
        if reasoning_steps:
            log = {
                "_id": str(uuid.uuid4()),
                "session_id": session_id,
                "message_index": len(conversation_history) // 2,
                "steps": reasoning_steps,
                "final_answer": final_answer,
                "context_ids": context_ids,
                "created_at": _now(),
            }
            await mongo.save_reasoning_log(log)
    except Exception as exc:  # noqa: BLE001
        logger.exception("intent run %s persistence failed: %s", run.run_id, exc)
        status = "error"
    finally:
        await run.finish(status)


# ---------------------------------------------------------------------------
# POST /api/intent/chat
# ---------------------------------------------------------------------------

@router.post("/api/intent/chat")
async def intent_chat(payload: dict):
    """Start a ReAct turn in the background and return an SSE stream observing it."""
    agent_id: str = payload.get("agent_id", "")
    user_message: str = payload.get("message", "").strip()
    session_id: str = payload.get("session_id") or str(uuid.uuid4())

    if not user_message:
        return {"ok": False, "error": "Empty message"}

    agent = _get_agent(agent_id)
    if not agent:
        return {"ok": False, "error": f"Agent '{agent_id}' not found"}

    _mcp_servers = agent.get("mcp_servers") or []
    mcp_url: str = _mcp_servers[0]["url"] if _mcp_servers else "http://localhost:8001/mcp"

    llm_settings = agent.get("llm_override") or _load_llm_settings()

    # Load or create session
    session = await mongo.get_session(session_id) or _mem_get(session_id)
    if not session:
        session = {
            "_id": session_id,
            "agent_id": agent_id,
            "agent_name": agent.get("name", agent_id),
            "session_type": "chat",
            "created_at": _now(),
            "updated_at": _now(),
            "messages": [],
            "status": "active",
        }

    conversation_history = session.get("messages", [])

    # Create the run and launch its executor as a detached task. The task is NOT
    # tied to this request: if the client disconnects, the run keeps going.
    run = run_manager.create(session_id, agent_id, user_message)
    run.task = asyncio.create_task(
        _execute_run(
            run,
            agent=agent,
            conversation_history=conversation_history,
            user_message=user_message,
            llm_settings=llm_settings,
            mcp_url=mcp_url,
            session=session,
            session_id=session_id,
        )
    )

    return StreamingResponse(
        run.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Session-Id": session_id,
            "X-Run-Id": run.run_id,
        },
    )


# ---------------------------------------------------------------------------
# GET /api/intent/stream/{run_id}  — reconnect to an in-flight / recent run
# ---------------------------------------------------------------------------

@router.get("/api/intent/stream/{run_id}")
async def intent_stream(run_id: str):
    """Reconnect to a run: replay everything emitted so far, then stream live."""
    run = run_manager.get(run_id)
    if not run:
        return {"ok": False, "error": "Run not found or expired"}
    return StreamingResponse(
        run.stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Session-Id": run.session_id,
            "X-Run-Id": run.run_id,
        },
    )


# ---------------------------------------------------------------------------
# GET /api/intent/active  — is there a run still in progress for this session?
# ---------------------------------------------------------------------------

@router.get("/api/intent/active")
async def intent_active(session_id: str):
    """Return the run still in progress for a session (used to resume on re-entry)."""
    run = run_manager.active_for_session(session_id)
    if not run:
        return {"ok": True, "run_id": None}
    return {
        "ok": True,
        "run_id": run.run_id,
        "status": run.status,
        "user_message": run.user_message,
    }


# ---------------------------------------------------------------------------
# GET /api/intent/sessions
# ---------------------------------------------------------------------------

@router.get("/api/intent/sessions")
async def list_sessions(agent_id: str = "", limit: int = 50):
    db_sessions = await mongo.list_sessions(agent_id or None, limit)
    if db_sessions:
        return {"ok": True, "sessions": db_sessions, "source": "mongodb"}
    mem = _mem_list(agent_id or None)
    return {"ok": True, "sessions": mem, "source": "memory"}


# ---------------------------------------------------------------------------
# GET /api/intent/sessions/{session_id}
# ---------------------------------------------------------------------------

@router.get("/api/intent/sessions/{session_id}")
async def get_session(session_id: str):
    doc = await mongo.get_session(session_id) or _mem_get(session_id)
    if not doc:
        return {"ok": False, "error": "Session not found"}
    logs = await mongo.get_reasoning_logs(session_id)
    doc["reasoning_logs"] = logs
    return {"ok": True, "session": doc}


# ---------------------------------------------------------------------------
# DELETE /api/intent/sessions/{session_id}
# ---------------------------------------------------------------------------

@router.delete("/api/intent/sessions/{session_id}")
async def delete_session(session_id: str):
    await mongo.delete_session(session_id)
    _mem_sessions.pop(session_id, None)
    return {"ok": True}
