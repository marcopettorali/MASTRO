"""Operational Context — REST endpoints for the context store.

Producers: GUI (Context page), CLI ('mastro context ...'), external
coordinator (OpenClaw through the CLI). Consumer: the ReAct prompt builder,
which injects active entries into every run's system prompt.

Validation at this boundary is deliberately strict: upstream of the CLI
there may be an LLM structuring free text (e.g. an operator message on a
chat channel relayed by OpenClaw), so a malformed or hallucinated entry
must be rejected here before it can pollute the agents' prompts.

Endpoints:
  GET    /api/context                       list entries (?include_history=, ?limit=)
  GET    /api/context/types                 supported entry types with defaults
  POST   /api/context                       add an entry
  POST   /api/context/{entry_id}/enable     re-enable a disabled entry
  POST   /api/context/{entry_id}/disable    disable without revoking (reversible)
  POST   /api/context/{entry_id}/revoke     revoke (kept in history, no delete)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..context_store import (
    CONTEXT_TYPES,
    SUMMARY_MAX_LEN,
    VALID_MODES,
    context_store,
    parse_iso,
)

router = APIRouter()
logger = logging.getLogger("mastro.context")


def _validate(payload: dict) -> dict:
    """Validate a creation payload against the closed type catalog.

    Raises HTTPException(400) with an explicit reason on any violation.
    Returns the normalized keyword arguments for ContextStore.add().
    """
    type_ = str(payload.get("type", "")).strip()
    if type_ not in CONTEXT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown context type '{type_}'. Valid types: {', '.join(sorted(CONTEXT_TYPES))}",
        )

    summary = str(payload.get("summary", "")).strip()
    if not summary:
        raise HTTPException(status_code=400, detail="Field 'summary' is required")
    if len(summary) > SUMMARY_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Field 'summary' exceeds {SUMMARY_MAX_LEN} characters",
        )

    mode = payload.get("mode")
    if mode is not None:
        mode = str(mode).strip()
        if mode not in VALID_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode '{mode}'. Valid modes: {', '.join(VALID_MODES)}",
            )

    payload_data = payload.get("payload")
    if payload_data is not None and not isinstance(payload_data, dict):
        raise HTTPException(status_code=400, detail="Field 'payload' must be a JSON object")

    source = str(payload.get("source", "api")).strip()[:64] or "api"

    valid_from = payload.get("valid_from")
    valid_until = payload.get("valid_until")
    dt_from = parse_iso(valid_from)
    dt_until = parse_iso(valid_until)
    if valid_from and dt_from is None:
        raise HTTPException(status_code=400, detail="Field 'valid_from' is not a valid ISO-8601 datetime")
    if valid_until and dt_until is None:
        raise HTTPException(status_code=400, detail="Field 'valid_until' is not a valid ISO-8601 datetime")
    if dt_from and dt_until and dt_until <= dt_from:
        raise HTTPException(status_code=400, detail="'valid_until' must be after 'valid_from'")

    return {
        "type_": type_,
        "summary": summary,
        "source": source,
        "payload": payload_data,
        "mode": mode,
        "valid_from": dt_from.isoformat() if dt_from else None,
        "valid_until": dt_until.isoformat() if dt_until else None,
    }


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@router.get("/api/context")
async def list_context(include_history: bool = True, limit: int = 200):
    entries = await context_store.list(include_history=include_history, limit=limit)
    return {"ok": True, "entries": entries}


@router.get("/api/context/types")
async def list_context_types():
    types = [
        {"type": name, "label": meta["label"], "default_mode": meta["mode"]}
        for name, meta in sorted(CONTEXT_TYPES.items())
    ]
    return {"ok": True, "types": types}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post("/api/context")
async def add_context(payload: dict):
    kwargs = _validate(payload)
    entry = await context_store.add(**kwargs)
    return {"ok": True, "entry": entry}


# ---------------------------------------------------------------------------
# Operator actions
# ---------------------------------------------------------------------------

@router.post("/api/context/{entry_id}/enable")
async def enable_context(entry_id: str, payload: dict | None = None):
    by = str((payload or {}).get("by", "gui")).strip()[:64] or "gui"
    entry = await context_store.set_enabled(entry_id, True, by=by)
    if not entry:
        raise HTTPException(status_code=404, detail="Context entry not found")
    return {"ok": True, "entry": entry}


@router.post("/api/context/{entry_id}/disable")
async def disable_context(entry_id: str, payload: dict | None = None):
    by = str((payload or {}).get("by", "gui")).strip()[:64] or "gui"
    entry = await context_store.set_enabled(entry_id, False, by=by)
    if not entry:
        raise HTTPException(status_code=404, detail="Context entry not found")
    return {"ok": True, "entry": entry}


@router.post("/api/context/{entry_id}/revoke")
async def revoke_context(entry_id: str, payload: dict | None = None):
    by = str((payload or {}).get("by", "gui")).strip()[:64] or "gui"
    entry = await context_store.revoke(entry_id, by=by)
    if not entry:
        raise HTTPException(status_code=404, detail="Context entry not found")
    return {"ok": True, "entry": entry}
