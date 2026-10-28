"""MASTRO MCP Gateway — external process managed by the backend."""
from __future__ import annotations

import collections
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from ..models import MCPStartRequest
import orchestrator as adapter
from ..paths import PROJECT_ROOT

router = APIRouter()

# ── MCP Gateway package path ──────────────────────────────────────────────────
MCP_GATEWAY_DIR = PROJECT_ROOT / "mcp_gateway"

# ── Process state (singleton) ─────────────────────────────────────────────────
_proc: Optional[subprocess.Popen] = None
_proc_lock = threading.Lock()
_proc_config: dict = {}

_log_buffer: collections.deque = collections.deque(maxlen=300)
_log_lock = threading.Lock()
_log_thread: Optional[threading.Thread] = None


def _is_running() -> bool:
    with _proc_lock:
        return _proc is not None and _proc.poll() is None


def _log_reader(proc: subprocess.Popen) -> None:
    """Thread that reads the MCP process stdout/stderr into a ring buffer."""
    try:
        for line in iter(proc.stdout.readline, ""):
            stripped = line.rstrip()
            if stripped:
                with _log_lock:
                    _log_buffer.append(stripped)
    except Exception:
        pass


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/mcp/start")
def mcp_start(req: MCPStartRequest):
    global _proc, _proc_config, _log_thread

    if _is_running():
        return {"ok": False, "error": "MCP server already running. Stop it first."}

    env = os.environ.copy()
    env["MOCK_MODE"] = "true" if req.mock_mode else "false"
    env["DRY_RUN"]   = "true" if req.dry_run   else "false"
    # The gateway reaches the MASTRO backend (gateway-management tools) at MASTRO_URL.
    env.setdefault("MASTRO_URL", "http://127.0.0.1:9100")

    try:
        env.update(adapter.gateway_environment(
            node_ids=req.node_ids, port=req.orchestrator_port, mock_mode=req.mock_mode,
        ))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    # Make the selected source adapter visible to the gateway subprocess.
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(PROJECT_ROOT), env.get("PYTHONPATH")]))

    if not MCP_GATEWAY_DIR.exists():
        return {"ok": False, "error": f"mcp_gateway directory not found: {MCP_GATEWAY_DIR}"}

    cmd = [sys.executable, "-m", "mastro_mcp_gateway"]
    if req.transport == "http":
        cmd += ["--http", "--port", str(req.port)]

    with _proc_lock:
        with _log_lock:
            _log_buffer.clear()
        try:
            _proc = subprocess.Popen(
                cmd,
                cwd=str(MCP_GATEWAY_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            _proc_config = {
                "mock_mode":  req.mock_mode,
                "dry_run":    req.dry_run,
                "transport":  req.transport,
                "port":       req.port,
                "node_ids":   req.node_ids,
                "orchestrator": adapter.describe(),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "url": (
                    f"http://localhost:{req.port}/mcp"
                    if req.transport == "http"
                    else "stdio"
                ),
            }
        except Exception as e:
            _proc = None
            return {"ok": False, "error": str(e)}

        _log_thread = threading.Thread(
            target=_log_reader, args=(_proc,), daemon=True
        )
        _log_thread.start()

    return {"ok": True, "pid": _proc.pid, "config": _proc_config}


@router.post("/api/mcp/stop")
def mcp_stop():
    global _proc

    with _proc_lock:
        if _proc is None or _proc.poll() is not None:
            _proc = None
            _proc_config.clear()
            return {"ok": False, "error": "MCP server not running."}
        try:
            _proc.terminate()
            try:
                _proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _proc.kill()
                _proc.wait(timeout=3)
        except Exception as e:
            return {"ok": False, "error": f"Error while stopping: {e}"}
        finally:
            _proc = None
            _proc_config.clear()

    return {"ok": True, "message": "MCP server stopped."}


@router.get("/api/mcp/status")
def mcp_status():
    with _proc_lock:
        running = _proc is not None and _proc.poll() is None
        pid     = _proc.pid if running else None
        config  = dict(_proc_config) if running else {}

    return {"ok": True, "running": running, "pid": pid, **config}


@router.get("/api/mcp/logs")
def mcp_logs(lines: int = 80):
    with _log_lock:
        buf = list(_log_buffer)
    return {"ok": True, "lines": buf[-lines:]}


@router.get("/api/mcp/nodes")
def mcp_available_nodes():
    """Return the adapter's normalized nodes for the selection panel."""
    return {"ok": True, "nodes": adapter.list_nodes()}
