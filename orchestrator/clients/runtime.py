"""
Client for the MOSAIC runtime (per-node process).
Covers all 17 endpoints exposed by each runtime node.
"""

import logging
from typing import Any

from ..config import cfg
from .base import _get, _post, _err

logger = logging.getLogger("mastro.mcp_gateway.runtime")


def _node_url(node_id: str, path: str) -> str:
    """Build the URL of a runtime endpoint of a specific node."""
    base = cfg.runtime_nodes.get(node_id)
    if not base:
        raise ValueError(
            f"Node '{node_id}' not found in MOSAIC_RUNTIME_NODES. "
            f"Known nodes: {list(cfg.runtime_nodes.keys())}"
        )
    return f"{base}{path}"


# ═══════════════════════════════════════════════════════════
#  HEALTH & STATUS
# ═══════════════════════════════════════════════════════════

async def health(node_id: str) -> dict:
    """GET /health — runtime health check (returns {ok: true})."""
    try:
        return await _get(_node_url(node_id, "/health"))
    except Exception as e:
        return _err(e, f"runtime_health[{node_id}]")


async def status(node_id: str) -> dict:
    """GET /status — current node status: active step and queue depth."""
    try:
        return await _get(_node_url(node_id, "/status"))
    except Exception as e:
        return _err(e, f"runtime_status[{node_id}]")


async def metrics(node_id: str) -> dict:
    """GET /metrics — node CPU% and RAM read from /proc (~0.5s refresh)."""
    try:
        return await _get(_node_url(node_id, "/metrics"))
    except Exception as e:
        return _err(e, f"runtime_metrics[{node_id}]")


async def node_info(node_id: str) -> dict:
    """GET /node-info — node hardware capabilities and catalog of available services."""
    try:
        return await _get(_node_url(node_id, "/node-info"))
    except Exception as e:
        return _err(e, f"runtime_node_info[{node_id}]")


# ═══════════════════════════════════════════════════════════
#  JOBS
# ═══════════════════════════════════════════════════════════

async def list_jobs(node_id: str) -> list[dict]:
    """GET /jobs — list of all jobs known to the node (including completed and failed ones)."""
    try:
        return await _get(_node_url(node_id, "/jobs"))
    except Exception as e:
        return [_err(e, f"runtime_list_jobs[{node_id}]")]


async def get_job(node_id: str, label: str, job_id: str) -> dict:
    """GET /jobs/{label}/{job_id} — job summary: status, lifetime, steps."""
    try:
        return await _get(_node_url(node_id, f"/jobs/{label}/{job_id}"))
    except Exception as e:
        return _err(e, f"runtime_get_job[{node_id}]")


async def list_job_steps(node_id: str, label: str, job_id: str) -> list[dict]:
    """GET /jobs/{label}/{job_id}/steps — list of all the steps of a job."""
    try:
        return await _get(_node_url(node_id, f"/jobs/{label}/{job_id}/steps"))
    except Exception as e:
        return [_err(e, f"runtime_list_steps[{node_id}]")]


async def get_step(node_id: str, label: str, job_id: str, counter: int) -> dict:
    """GET /jobs/{label}/{job_id}/{counter} — detailed status of a step."""
    try:
        return await _get(_node_url(node_id, f"/jobs/{label}/{job_id}/{counter}"))
    except Exception as e:
        return _err(e, f"runtime_get_step[{node_id}]")


async def get_step_input(node_id: str, label: str, job_id: str, counter: int) -> dict:
    """GET /jobs/{label}/{job_id}/{counter}/input — input payload of a step."""
    try:
        return await _get(_node_url(node_id, f"/jobs/{label}/{job_id}/{counter}/input"))
    except Exception as e:
        return _err(e, f"runtime_get_step_input[{node_id}]")


async def get_step_output(node_id: str, label: str, job_id: str, counter: int) -> dict:
    """GET /jobs/{label}/{job_id}/{counter}/output — output payload of a step."""
    try:
        return await _get(_node_url(node_id, f"/jobs/{label}/{job_id}/{counter}/output"))
    except Exception as e:
        return _err(e, f"runtime_get_step_output[{node_id}]")


# ═══════════════════════════════════════════════════════════
#  JOB EXECUTION (write)
# ═══════════════════════════════════════════════════════════

async def execute(node_id: str, label: str, job_id: str, counter: int, input_data: dict) -> dict:
    """
    POST /execute — launches a new job (pipeline entry point).
    Used by traffic generators and by clients that know the input structure.
    """
    try:
        payload = {
            "label": label,
            "job_id": job_id,
            "counter": counter,
            "input": input_data,
        }
        return await _post(_node_url(node_id, "/execute"), payload)
    except Exception as e:
        return _err(e, f"runtime_execute[{node_id}]")


async def forward_input(
    node_id: str, label: str, job_id: str, counter: int, input_data: dict
) -> dict:
    """
    POST /input — receives the output of a previous step (inter-node forwarding).
    Not normally called directly; handled by the runtime within the pipeline flow.
    """
    try:
        payload = {
            "label": label,
            "job_id": job_id,
            "counter": counter,
            "input": input_data,
        }
        return await _post(_node_url(node_id, "/input"), payload)
    except Exception as e:
        return _err(e, f"runtime_forward_input[{node_id}]")


# ═══════════════════════════════════════════════════════════
#  LOGS
# ═══════════════════════════════════════════════════════════

async def drain_logs(node_id: str) -> list[dict]:
    """
    POST /logs/drain — collects and empties the node's JSONL log buffer.
    The orchestrator calls this every 3s; calling it manually resets the buffer.
    """
    try:
        result = await _post(_node_url(node_id, "/logs/drain"))
        return result if isinstance(result, list) else [result]
    except Exception as e:
        return [_err(e, f"runtime_drain_logs[{node_id}]")]


# ═══════════════════════════════════════════════════════════
#  TRAFFIC GENERATORS (runtime-level)
# ═══════════════════════════════════════════════════════════

async def start_tg(node_id: str, label: str, tg_ref: str, iterations: int = -1, interval_s: float = 1.0) -> dict:
    """POST /traffic-generator/start — starts a TG on the node's runtime."""
    try:
        return await _post(_node_url(node_id, "/traffic-generator/start"), {
            "label": label,
            "tg_ref": tg_ref,
            "iterations": iterations,
            "interval": interval_s,
        })
    except Exception as e:
        return _err(e, f"runtime_start_tg[{node_id}]")


async def stop_tg(node_id: str, label: str) -> dict:
    """POST /traffic-generator/stop — stops the TG for a given label."""
    try:
        return await _post(_node_url(node_id, "/traffic-generator/stop"), {
            "label": label,
        })
    except Exception as e:
        return _err(e, f"runtime_stop_tg[{node_id}]")


async def get_tg_status(node_id: str, label: str) -> dict:
    """GET /traffic-generator/status?label={label} — TG status for a given label."""
    try:
        return await _get(_node_url(node_id, "/traffic-generator/status"),
                          params={"label": label})
    except Exception as e:
        return _err(e, f"runtime_tg_status[{node_id}]")


async def list_tg(node_id: str) -> list[dict]:
    """GET /traffic-generator/list — list of the traffic generators available on the node."""
    try:
        return await _get(_node_url(node_id, "/traffic-generator/list"))
    except Exception as e:
        return [_err(e, f"runtime_list_tg[{node_id}]")]
