"""
MCP tools — Monitoring: system status, metrics, logs, node info.
Covers: GET /api/status, /api/metrics, /api/jobs, /api/ping,
        /api/logs, GET /api/nodes-info + per-node runtime endpoints.
All tools are read-only and safe to call at high frequency.
"""

import logging

from fastmcp import FastMCP

from ..config import cfg
from ..clients import orchestrator as orch
from ..clients import runtime as rt
from ..mock.data import (
    MOCK_STATUS, mock_metrics, mock_runtime_status,
    mock_node_info, mock_runtime_metrics,
)

logger = logging.getLogger("mastro.mcp_gateway.tools.monitoring")


def register(mcp: FastMCP) -> None:

    # ── /api/status ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_get_system_status() -> dict:
        """
        Aggregated status of the whole MOSAIC system: online/offline nodes,
        active steps and queued steps for each node.
        Call it at the start of every tick to get an overall picture.
        """
        if cfg.mock_mode:
            return MOCK_STATUS
        return await orch.get_status()

    # ── /api/metrics ─────────────────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_get_all_metrics() -> dict:
        """
        CPU%, RAM usage (used/free/total in bytes), CPU temperature (temp_c,
        degrees Celsius) and power draw (power_w, Watts) for all nodes,
        from the orchestrator cache (refreshed every ~1s). The
        "telemetry" field reports the temperature and power source (sysfs/rapl,
        synthetic, +override).
        Use this for a quick overview before drilling into a specific node.
        """
        if cfg.mock_mode:
            return mock_metrics()
        return await orch.get_all_metrics()

    # ── /api/jobs ────────────────────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_get_all_jobs(timeout: float = 5.0) -> dict:
        """
        All active, queued and recently completed jobs on all nodes,
        with created_at, label, job_id and status.
        Useful to understand the overall load of the system.

        Args:
            timeout: node polling timeout in seconds (default 5.0)
        """
        if cfg.mock_mode:
            from ..mock.data import mock_jobs
            return {"ok": True, "jobs": {"fog1": {"jobs": mock_jobs("inference_pipeline")}}}
        return await orch.get_jobs(timeout=timeout)

    # ── /api/ping ─────────────────────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_ping() -> dict:
        """
        Health check of the MOSAIC GUI backend.
        Returns {ok: true} if the backend is reachable.
        Call it before any operation to verify connectivity.
        """
        if cfg.mock_mode:
            return {"ok": True}
        return await orch.ping()

    # ── /api/logs ─────────────────────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_get_logs(limit: int = 50) -> dict:
        """
        Last N JSONL logs collected by the orchestrator from all nodes.
        Logs include step execution events, errors and system messages.

        Args:
            limit: maximum number of logs to return (default 50)
        """
        if cfg.mock_mode:
            from ..mock.data import mock_logs
            return {"ok": True, "logs": mock_logs(lines=limit)}
        return await orch.get_logs(limit=limit)

    # ── /api/nodes-info ───────────────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_get_nodes_info() -> dict:
        """
        Full configuration of all nodes (nodes_info.json):
        host, ports, runtime_dir, service_catalogs, SSH credentials.
        Use it to discover the available nodes before deploy or sync operations.
        """
        if cfg.mock_mode:
            from ..mock.data import MOCK_NODES_CONFIG
            return {"ok": True, "nodes_info": MOCK_NODES_CONFIG}
        return await orch.get_nodes_info()

    # ── Per-node runtime ──────────────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_get_node_metrics(node_id: str) -> dict:
        """
        Read the metrics directly from a specific node's runtime
        (cpu_pct, cpu_states, mem_used, mem_free, mem_total in bytes, plus
        temp_c in degrees Celsius and power_w in Watts, with their source
        in the "telemetry" field).
        Fresher than the orchestrator cache (~0.5s vs ~1s).

        Args:
            node_id: node ID (e.g. "fog1", "fog2", "server")
        """
        if cfg.mock_mode:
            return mock_runtime_metrics(node_id)
        return await rt.metrics(node_id)

    @mcp.tool()
    async def mosaic_get_node_status(node_id: str) -> dict:
        """
        Current status of a node's runtime: running steps
        (label, job_id, counter, service, started_at) and queue depth.
        Useful to tell whether a node is saturated or idle.

        Args:
            node_id: node ID (e.g. "fog1")
        """
        if cfg.mock_mode:
            return mock_runtime_status(node_id)
        return await rt.status(node_id)

    @mcp.tool()
    async def mosaic_get_node_info(node_id: str) -> dict:
        """
        Hardware capabilities of the node (CPU cores, RAM, GPU, Docker)
        and catalog of available services with mode and Docker image.
        Use it before deciding whether to move a workload to this node.

        Args:
            node_id: node ID (e.g. "fog1")
        """
        if cfg.mock_mode:
            return mock_node_info(node_id)
        return await rt.node_info(node_id)

    @mcp.tool()
    async def mosaic_check_node_health(node_id: str) -> dict:
        """
        Health check of a node's runtime.
        Returns {ok: true} if the runtime process is reachable, an error otherwise.
        Call it before operations that require the node to be online.

        Args:
            node_id: node ID
        """
        if cfg.mock_mode:
            return {"ok": True, "node_id": node_id}
        return await rt.health(node_id)

    @mcp.tool()
    async def mosaic_get_all_nodes_status() -> dict:
        """
        Full snapshot of all nodes: runtime status + CPU/RAM metrics.
        Aggregates several calls into one to reduce the tick latency.
        """
        if cfg.mock_mode:
            nodes = list(MOCK_STATUS["nodes"].keys())
        else:
            config = await orch.get_nodes_info()
            if "error" in config:
                return config
            nodes = list(config.get("nodes_info", {}).get("nodes", {}).keys())

        result: dict = {}
        for node_id in nodes:
            if cfg.mock_mode:
                result[node_id] = {
                    "status": mock_runtime_status(node_id),
                    "metrics": mock_runtime_metrics(node_id),
                }
            else:
                result[node_id] = {
                    "status": await rt.status(node_id),
                    "metrics": await rt.metrics(node_id),
                }
        return result
