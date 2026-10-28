"""LLM Agent Module — Agent CRUD, Skill management, LLM & MongoDB config."""
from __future__ import annotations

import json
import logging
import uuid
from copy import deepcopy

from fastapi import APIRouter, HTTPException

from ..paths import AGENTS_CONFIG_PATH, LLM_SETTINGS_PATH, MONGODB_CONFIG_PATH, SKILLS_DIR
from ..agent.skill_loader import list_skills, get_skill_content, save_skill, delete_skill
from ..agent.scheduler import scheduler
from ..db import mongo

router = APIRouter()
logger = logging.getLogger("mastro.llm_agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_agents() -> list[dict]:
    if not AGENTS_CONFIG_PATH.exists():
        return []
    try:
        return json.loads(AGENTS_CONFIG_PATH.read_text(encoding="utf-8")).get("agents", [])
    except Exception:
        return []


def _save_agents(agents: list[dict]) -> None:
    AGENTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENTS_CONFIG_PATH.write_text(
        json.dumps({"agents": agents}, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_json(path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ===========================================================================
# AGENTS
# ===========================================================================

@router.get("/api/agents")
def api_list_agents():
    return {"ok": True, "agents": _load_agents()}


@router.post("/api/agents")
async def api_create_agent(payload: dict):
    agents = _load_agents()
    new_agent = {
        "id": str(uuid.uuid4()),
        "name": payload.get("name", "New Agent"),
        "description": payload.get("description", ""),
        "system_prompt": payload.get("system_prompt", "You are a MASTRO agent operating managed infrastructure."),
        "skills": payload.get("skills", []),
        "mcp_servers": payload.get("mcp_servers", []),
        "llm_override": payload.get("llm_override") or None,
        "autonomous": payload.get("autonomous") or None,
    }
    agents.append(new_agent)
    _save_agents(agents)
    await scheduler.reload()
    return {"ok": True, "agent": new_agent}


@router.get("/api/agents/{agent_id}")
def api_get_agent(agent_id: str):
    for a in _load_agents():
        if a["id"] == agent_id:
            return {"ok": True, "agent": a}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.put("/api/agents/{agent_id}")
async def api_update_agent(agent_id: str, payload: dict):
    agents = _load_agents()
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            agents[i] = {
                "id": agent_id,
                "name": payload.get("name", a.get("name", "")),
                "description": payload.get("description", a.get("description", "")),
                "system_prompt": payload.get("system_prompt", a.get("system_prompt", "")),
                "skills": payload.get("skills", a.get("skills", [])),
                "mcp_servers": payload.get("mcp_servers", a.get("mcp_servers", [])),
                "llm_override": payload.get("llm_override") or a.get("llm_override"),
                "autonomous": payload.get("autonomous", a.get("autonomous")) or None,
            }
            _save_agents(agents)
            await scheduler.reload()
            return {"ok": True, "agent": agents[i]}
    raise HTTPException(status_code=404, detail="Agent not found")


@router.delete("/api/agents/{agent_id}")
async def api_delete_agent(agent_id: str):
    agents = _load_agents()
    new_agents = [a for a in agents if a["id"] != agent_id]
    if len(new_agents) == len(agents):
        raise HTTPException(status_code=404, detail="Agent not found")
    _save_agents(new_agents)
    await scheduler.reload()
    return {"ok": True}


# ===========================================================================
# SKILLS
# ===========================================================================

@router.get("/api/skills")
def api_list_skills():
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skills = list_skills(SKILLS_DIR)
    return {"ok": True, "skills": skills}


@router.get("/api/skills/{skill_name}")
def api_get_skill(skill_name: str):
    content = get_skill_content(skill_name, SKILLS_DIR)
    if content is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"ok": True, "name": skill_name, "content": content}


@router.post("/api/skills")
def api_create_skill(payload: dict):
    name = payload.get("name", "").strip().lower().replace(" ", "-")
    if not name:
        raise HTTPException(status_code=400, detail="Skill name required")
    content = payload.get("content", f"---\nname: {name}\ndescription: {payload.get('description','')}\n---\n\n# {name}\n\nAdd skill instructions here.\n")
    save_skill(name, content, SKILLS_DIR)
    return {"ok": True, "name": name}


@router.put("/api/skills/{skill_name}")
def api_update_skill(skill_name: str, payload: dict):
    content = payload.get("content")
    if content is None:
        raise HTTPException(status_code=400, detail="content required")
    save_skill(skill_name, content, SKILLS_DIR)
    return {"ok": True}


@router.delete("/api/skills/{skill_name}")
def api_delete_skill(skill_name: str):
    ok = delete_skill(skill_name, SKILLS_DIR)
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"ok": True}


# ===========================================================================
# LLM SETTINGS
# ===========================================================================

@router.get("/api/config/llm")
def api_get_llm():
    return {"ok": True, "settings": _load_json(LLM_SETTINGS_PATH)}


@router.post("/api/config/llm")
def api_save_llm(payload: dict):
    settings = payload.get("settings", payload)
    _save_json(LLM_SETTINGS_PATH, settings)
    return {"ok": True}


# ===========================================================================
# MONGODB CONFIG
# ===========================================================================

@router.get("/api/config/mongodb")
def api_get_mongodb():
    cfg = _load_json(MONGODB_CONFIG_PATH)
    return {"ok": True, "config": cfg}


@router.post("/api/config/mongodb")
def api_save_mongodb(payload: dict):
    cfg = payload.get("config", payload)
    _save_json(MONGODB_CONFIG_PATH, cfg)
    return {"ok": True}


@router.post("/api/config/mongodb/test")
async def api_test_mongodb(payload: dict):
    uri = payload.get("uri", "")
    db_name = payload.get("database", "mastro_agent")
    if not uri:
        return {"ok": False, "message": "URI is required"}
    ok, msg = await mongo.test_connection(uri, db_name)
    return {"ok": ok, "message": msg}


# ===========================================================================
# MCP SERVER TEST (used from Agents & Skills UI)
# ===========================================================================

@router.post("/api/mcp/test")
async def api_test_mcp(payload: dict):
    """Test an MCP server URL: call tools/list and return tool count + names."""
    url = payload.get("url", "").strip()
    if not url:
        return {"ok": False, "message": "URL is required"}
    try:
        from ..agent.mcp_bridge import list_tools
        tools = await list_tools(url)
        if tools:
            names = [t["name"] for t in tools[:10]]
            extra = len(tools) - 10 if len(tools) > 10 else 0
            summary = ", ".join(names) + (f" … +{extra} more" if extra else "")
            return {"ok": True, "tool_count": len(tools),
                    "message": f"Connected — {len(tools)} tool(s) available: {summary}"}
        else:
            return {"ok": False, "message": "Server reachable but returned no tools. Is it a valid MCP server?"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
