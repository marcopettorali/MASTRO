"""
MCP tools — Operations: Jobs, Config (write), Recording, Traffic Generator (runtime),
            Runtime job inspection, Log management, Launch.
Covers the remaining endpoints of routers/jobs.py, recording.py, config.py (write),
tg.py (start/stop/status), monitoring.py (jobs) and the per-node runtime (job ops).
"""

import logging

from fastmcp import FastMCP

from ..config import cfg
from ..clients import orchestrator as orch
from ..clients import runtime as rt
from ..mock.data import mock_jobs, mock_job_detail, mock_logs, mock_tg_status

logger = logging.getLogger("mastro.mcp_gateway.tools.ops")

_MAX_LIST_LIMIT = 200


def _paginate(items: list, limit: int, offset: int, key: str) -> dict:
    """Safely truncate a long list so it fits in the LLM context.

    Sorts by created_at descending (most recent first, so a typical
    intent such as "what is happening right now" stays correct even when
    truncated), applies offset/limit and returns explicit pagination
    metadata so the model knows whether more items are available.
    """
    limit = max(1, min(int(limit), _MAX_LIST_LIMIT))
    offset = max(0, int(offset))
    ordered = sorted(items, key=lambda j: (j.get("created_at") or ""), reverse=True)
    total = len(ordered)
    page = ordered[offset:offset + limit]
    return {
        key: page,
        "pagination": {
            "total_count": total,
            "returned_count": len(page),
            "offset": offset,
            "limit": limit,
            "truncated": offset + len(page) < total,
        },
    }


def register(mcp: FastMCP) -> None:

    # ════════════════════════════════════════════════════════
    #  JOBS — Orchestrator level  (routers/jobs.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_get_job_list(
        label: str, limit: int = 20, offset: int = 0, timeout: float = 10.0
    ) -> dict:
        """
        Most recent jobs (job_id and status) for a specific pipeline,
        sorted by created_at descending. Queries the last node of the pipeline.

        The response is paginated: at most `limit` jobs per call (default 20,
        cap 200), so the context is not flooded when the pipeline has a long
        queue (e.g. under heavy load or saturation). The "pagination" field
        reports "total_count" and "truncated": if "truncated" is true, repeat the
        call with a larger "offset" to see older jobs.

        Args:
            label: pipeline name (e.g. "inference_pipeline")
            limit: maximum number of jobs to return (default 20, cap 200)
            offset: how many of the most recent jobs to skip, to page through the list (default 0)
            timeout: timeout in seconds (default 10.0)
        """
        if cfg.mock_mode:
            jobs = mock_jobs(label)
            page = _paginate(jobs, limit, offset, "jobs")
            return {"ok": True, "label": label, **page}
        result = await orch.get_job_list(label=label, timeout=timeout)
        if isinstance(result, dict) and isinstance(result.get("jobs"), list):
            page = _paginate(result["jobs"], limit, offset, "jobs")
            result.update(page)
        return result

    @mcp.tool()
    async def mosaic_get_job_results(
        label: str, limit: int = 20, offset: int = 0, timeout: float = 10.0
    ) -> dict:
        """
        Output of the most recent jobs of a pipeline (includes the output
        payload for completed jobs, so it is heavier than
        mosaic_get_job_list). Queries the last step of the pipeline.

        Paginated like mosaic_get_job_list: at most `limit` jobs (default 20,
        cap 200), most recent first. With a long queue, call
        mosaic_get_job_list first to see how many jobs there are, then request
        only the range of interest here.

        Args:
            label: pipeline name
            limit: maximum number of jobs to return (default 20, cap 200)
            offset: how many of the most recent jobs to skip, to page through the list (default 0)
            timeout: timeout in seconds (default 10.0)
        """
        if cfg.mock_mode:
            jobs = mock_jobs(label)
            results = [
                {"job_id": j["job_id"], "status": j["status"], "created_at": j.get("created_at"),
                 "output": {"result": "mock_output"} if j["status"] == "done" else None}
                for j in jobs
            ]
            page = _paginate(results, limit, offset, "results")
            return {"ok": True, "label": label, **page}
        result = await orch.get_job_results(label=label, timeout=timeout)
        if isinstance(result, dict) and isinstance(result.get("results"), list):
            page = _paginate(result["results"], limit, offset, "results")
            result.update(page)
        return result

    @mcp.tool()
    async def mosaic_get_job_timeline(
        label: str, job_id: str, timeout: float = 10.0
    ) -> dict:
        """
        Detailed timeline of a job: for each step returns
        queue_ms, exec_ms, transmission_ms, overhead_ms and the related logs.
        Use it to diagnose bottlenecks in the pipeline.

        Args:
            label: pipeline name
            job_id: job ID
            timeout: timeout in seconds (default 10.0)
        """
        if cfg.mock_mode:
            return mock_job_detail(label, job_id)
        return await orch.get_job_timeline(label=label, job_id=job_id, timeout=timeout)

    @mcp.tool()
    async def mosaic_get_step_data(
        label: str, job_id: str, counter: int, node_id: str,
        timeout: float = 10.0,
    ) -> dict:
        """
        JSON input and output of a specific step on a specific node.
        Use it to inspect the intermediate payloads of the pipeline (Step Inspector).

        Args:
            label: pipeline name
            job_id: job ID
            counter: step index (0-based)
            node_id: ID of the node that executed the step
            timeout: timeout in seconds (default 10.0)
        """
        if cfg.mock_mode:
            return {
                "ok": True, "label": label, "job_id": job_id,
                "counter": counter, "node_id": node_id,
                "input": {"mock": "input_data"},
                "output": {"mock": "output_data"},
            }
        return await orch.get_step_data(
            label=label, job_id=job_id,
            counter=counter, node_id=node_id, timeout=timeout,
        )

    @mcp.tool()
    async def mosaic_launch_job() -> dict:
        """
        Manually launch a job using the current inputs.json file.
        Equivalent to the "Launch" button in the GUI. Use it after updating
        the inputs with mosaic_save_inputs.
        """
        if cfg.mock_mode:
            return {"ok": True, "result": {"launched": True, "job_id": "mock-job-001"}}
        return await orch.launch_job()

    @mcp.tool()
    async def mosaic_get_tg_deployments() -> dict:
        """
        Map node → list of TGs tracked in tg_deployments.json.
        Shows which traffic generators have been deployed on which nodes.
        """
        if cfg.mock_mode:
            return {"ok": True, "tg_deployments": {"fog1": ["inference_tg"], "fog2": []}}
        return await orch.get_tg_deployments()

    # ════════════════════════════════════════════════════════
    #  CONFIG — Write  (routers/config.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_save_nodes_info(nodes_info: dict) -> dict:
        """
        Overwrite nodes_info.json with the given configuration.
        WARNING: critical operation — updates hosts, ports, service_catalogs
        and SSH credentials of all nodes.
        Read it first with mosaic_get_nodes_info to start from the current structure.

        Args:
            nodes_info: full nodes_info structure (the "nodes" key is required)
        """
        if cfg.dry_run:
            return {"dry_run": True, "message": "save_nodes_info: no changes applied"}
        if cfg.mock_mode:
            return {"ok": True, "message": "nodes_info.json saved (mock)"}
        return await orch.save_nodes_info(nodes_info=nodes_info)

    @mcp.tool()
    async def mosaic_get_inputs() -> dict:
        """
        Content of inputs.json: raw text, parsed JSON and the valid_json flag.
        Use it before mosaic_launch_job to check the current inputs.
        """
        if cfg.mock_mode:
            return {"ok": True, "raw_text": '{"data": "mock_input"}', "valid_json": True}
        return await orch.get_inputs()

    @mcp.tool()
    async def mosaic_save_inputs(raw_text: str) -> dict:
        """
        Save inputs.json with the given text (must be valid JSON).
        Use it before mosaic_launch_job to set the job inputs.

        Args:
            raw_text: JSON content to save as inputs.json
        """
        if cfg.dry_run:
            return {"dry_run": True, "message": "save_inputs: no changes applied"}
        if cfg.mock_mode:
            return {"ok": True, "message": "inputs.json saved (mock)", "valid_json": True}
        return await orch.save_inputs(raw_text=raw_text)

    # ════════════════════════════════════════════════════════
    #  LOGS — Management  (routers/recording.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_clear_logs(node_id: str | None = None) -> dict:
        """
        Clear the logs collected by the orchestrator.
        If node_id is given, only that node's logs are deleted;
        otherwise all logs of all nodes are deleted.

        Args:
            node_id: node ID (None = all nodes)
        """
        if cfg.dry_run:
            return {"dry_run": True, "message": "clear_logs: no changes applied"}
        if cfg.mock_mode:
            return {"ok": True, "message": f"Logs cleared for {node_id or 'all nodes'} (mock)"}
        return await orch.clear_logs(node_id=node_id)

    # ════════════════════════════════════════════════════════
    #  RECORDING — Metrics  (routers/recording.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_start_metrics_recording(
        interval_seconds: float = 1.0,
        duration_seconds: int = 0,
    ) -> dict:
        """
        Start a CPU/RAM recording session to a CSV file.
        If duration_seconds=0 the recording continues until it is stopped manually.

        Args:
            interval_seconds: sampling interval in seconds (min 0.5)
            duration_seconds: maximum duration in seconds (0 = unlimited)
        """
        if cfg.mock_mode:
            return {"ok": True, "message": "Recording started (mock)", "status": {"running": True}}
        return await orch.start_metrics_recording(
            interval_seconds=interval_seconds,
            duration_seconds=duration_seconds,
        )

    @mcp.tool()
    async def mosaic_stop_metrics_recording() -> dict:
        """
        Stop the current metrics recording session.
        The CSV file is finalized and saved in metrics_recordings/.
        """
        if cfg.mock_mode:
            return {"ok": True, "message": "Recording stopped (mock)"}
        return await orch.stop_metrics_recording()

    @mcp.tool()
    async def mosaic_get_metrics_recording_status() -> dict:
        """
        Status of the current metrics recording session
        (running, filename, elapsed, samples_collected).
        """
        if cfg.mock_mode:
            return {"ok": True, "status": {"running": False, "filename": None}}
        return await orch.get_metrics_recording_status()

    @mcp.tool()
    async def mosaic_get_metrics_recording_list() -> dict:
        """
        List of recorded metrics CSV files, sorted by date descending.
        """
        if cfg.mock_mode:
            return {"ok": True, "files": ["metrics_20240101_120000.csv"]}
        return await orch.get_metrics_recording_list()

    # ════════════════════════════════════════════════════════
    #  RECORDING — Performance  (routers/recording.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_start_performance_recording(
        duration_seconds: int = 0,
        label_filter: str | None = None,
        label_filters: list[str] | None = None,
    ) -> dict:
        """
        Start a job timing recording session (end-to-end latencies) to CSV.
        Can filter by one or more pipelines.

        Args:
            duration_seconds: maximum duration in seconds (0 = unlimited)
            label_filter: filter by a single pipeline (e.g. "inference_pipeline")
            label_filters: filter by several pipelines at once
        """
        if cfg.mock_mode:
            return {"ok": True, "message": "Performance recording started (mock)"}
        return await orch.start_performance_recording(
            duration_seconds=duration_seconds,
            label_filter=label_filter,
            label_filters=label_filters,
        )

    @mcp.tool()
    async def mosaic_stop_performance_recording() -> dict:
        """
        Stop the current performance recording session.
        The CSV file is finalized in perf_recordings/.
        """
        if cfg.mock_mode:
            return {"ok": True, "message": "Performance recording stopped (mock)"}
        return await orch.stop_performance_recording()

    @mcp.tool()
    async def mosaic_get_performance_recording_status() -> dict:
        """
        Status of the current performance recording session
        (running, filename, jobs_recorded, label_filters).
        """
        if cfg.mock_mode:
            return {"ok": True, "status": {"running": False}}
        return await orch.get_performance_recording_status()

    @mcp.tool()
    async def mosaic_get_performance_recordings_list() -> dict:
        """
        List of recorded performance CSV files, sorted by date descending.
        """
        if cfg.mock_mode:
            return {"ok": True, "files": ["perf_inference_pipeline_20240101_120000.csv"]}
        return await orch.get_performance_recordings_list()

    # ════════════════════════════════════════════════════════
    #  TRAFFIC GENERATOR — Runtime  (routers/tg.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_get_tg_list_local() -> dict:
        """
        Traffic generators available locally on the orchestrator
        (subdirectories of traffic_generators/ containing traffic_generator.py).
        """
        if cfg.mock_mode:
            return {"ok": True, "traffic_generators": ["inference_tg", "stress_tg"]}
        return await orch.get_tg_list_local()

    @mcp.tool()
    async def mosaic_start_traffic_generator(
        node_id: str,
        label: str,
        tg_ref: str,
        iterations: int = -1,
        interval: float = 1.0,
    ) -> dict:
        """
        Start a traffic generator on a node's runtime.
        iterations=-1 means an infinite loop.

        Args:
            node_id: ID of the node on which to start the TG
            label: pipeline label (used as the label of the generated jobs)
            tg_ref: name of the TG to start (must already be deployed on the node)
            iterations: number of iterations (-1 = infinite)
            interval: interval between consecutive jobs, in seconds
        """
        if cfg.mock_mode:
            return {"ok": True, "node_id": node_id, "label": label, "tg_ref": tg_ref}
        return await orch.start_traffic_generator(
            node_id=node_id, label=label, tg_ref=tg_ref,
            iterations=iterations, interval=interval,
        )

    @mcp.tool()
    async def mosaic_stop_traffic_generator(node_id: str, label: str) -> dict:
        """
        Stop the traffic generator for a given label on a node.

        Args:
            node_id: node ID
            label: pipeline label (identifies the TG to stop)
        """
        if cfg.mock_mode:
            return {"ok": True, "node_id": node_id, "label": label}
        return await orch.stop_traffic_generator(node_id=node_id, label=label)

    @mcp.tool()
    async def mosaic_get_traffic_generator_status(label: str | None = None) -> dict:
        """
        Status of the traffic generators on all nodes.
        If label is given, filters by that pipeline.

        Args:
            label: filter by pipeline (None = all)
        """
        if cfg.mock_mode:
            return mock_tg_status(label)
        return await orch.get_traffic_generator_status(label=label)

    @mcp.tool()
    async def mosaic_get_traffic_generator_list(
        nodes: list[str] | None = None,
    ) -> dict:
        """
        TGs available on the node runtimes (queries the runtime of each node).

        Args:
            nodes: list of nodes to query (None = all)
        """
        if cfg.mock_mode:
            return {"ok": True, "nodes": {"fog1": {"traffic_generators": ["inference_tg"]}}}
        return await orch.get_traffic_generator_list(nodes=nodes)

    # ════════════════════════════════════════════════════════
    #  RUNTIME — Per-node job inspection  (clients/runtime.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_list_node_jobs(node_id: str) -> list[dict]:
        """
        List of all jobs known to a specific node's runtime
        (including completed and failed ones).

        Args:
            node_id: node ID
        """
        if cfg.mock_mode:
            return mock_jobs("inference_pipeline")
        return await rt.list_jobs(node_id)

    @mcp.tool()
    async def mosaic_get_node_job(node_id: str, label: str, job_id: str) -> dict:
        """
        Summary of a job on a node's runtime: status, total lifetime, steps.

        Args:
            node_id: node ID
            label: pipeline name
            job_id: job ID
        """
        if cfg.mock_mode:
            return mock_job_detail(label, job_id)
        return await rt.get_job(node_id, label, job_id)

    @mcp.tool()
    async def mosaic_get_node_job_steps(
        node_id: str, label: str, job_id: str
    ) -> list[dict]:
        """
        List of all the steps of a job on a node's runtime.

        Args:
            node_id: node ID
            label: pipeline name
            job_id: job ID
        """
        if cfg.mock_mode:
            return [{"counter": 0, "status": "done"}, {"counter": 1, "status": "done"}]
        return await rt.list_job_steps(node_id, label, job_id)

    @mcp.tool()
    async def mosaic_get_node_step(
        node_id: str, label: str, job_id: str, counter: int
    ) -> dict:
        """
        Detailed status of a step on a node's runtime.

        Args:
            node_id: node ID
            label: pipeline name
            job_id: job ID
            counter: step index
        """
        if cfg.mock_mode:
            return {"counter": counter, "status": "done", "exec_ms": 42}
        return await rt.get_step(node_id, label, job_id, counter)

    @mcp.tool()
    async def mosaic_get_node_step_input(
        node_id: str, label: str, job_id: str, counter: int
    ) -> dict:
        """
        Input payload of a step on the runtime (raw data received by the step).

        Args:
            node_id: node ID
            label: pipeline name
            job_id: job ID
            counter: step index
        """
        if cfg.mock_mode:
            return {"input": {"mock": "input_payload"}}
        return await rt.get_step_input(node_id, label, job_id, counter)

    @mcp.tool()
    async def mosaic_get_node_step_output(
        node_id: str, label: str, job_id: str, counter: int
    ) -> dict:
        """
        Output payload of a step on the runtime (data produced by the step).

        Args:
            node_id: node ID
            label: pipeline name
            job_id: job ID
            counter: step index
        """
        if cfg.mock_mode:
            return {"output": {"mock": "output_payload"}}
        return await rt.get_step_output(node_id, label, job_id, counter)

    @mcp.tool()
    async def mosaic_drain_node_logs(node_id: str) -> list[dict]:
        """
        Collect and empty the JSONL log buffer of a node's runtime.
        The orchestrator calls it every ~3s; calling it manually resets the buffer.

        Args:
            node_id: node ID
        """
        if cfg.mock_mode:
            return mock_logs(node_id)[:5]
        return await rt.drain_logs(node_id)
