"""
Client for the MOSAIC GUI/Orchestrator backend.
URL paths mirror EXACTLY the routes defined in the MOSAIC backend (gui/backend/routers/ in the MOSAIC repository).
Do not change the backend: adapting to it is this file's job.
"""

import logging
from typing import Any

from ..config import cfg
from .base import _get, _post, _delete, _err

logger = logging.getLogger("mastro.mcp_gateway.orchestrator")


def _url(path: str) -> str:
    """Build the full URL from the backend path."""
    return f"{cfg.orchestrator_base_url}{path}"


# ════════════════════════════════════════════════════════════
#  MONITORING  (routers/monitoring.py)
# ════════════════════════════════════════════════════════════

async def get_status(timeout: float = 5.0) -> dict:
    """GET /api/status — aggregated node status (online/offline, active/queued steps)."""
    try:
        return await _get(_url("/api/status"), params={"timeout": timeout})
    except Exception as e:
        return _err(e, "get_status")


async def get_all_metrics(timeout: float = 5.0) -> dict:
    """GET /api/metrics — CPU% and RAM of all nodes (~1s poller cache)."""
    try:
        return await _get(_url("/api/metrics"), params={"timeout": timeout})
    except Exception as e:
        return _err(e, "get_all_metrics")


async def get_jobs(timeout: float = 5.0) -> dict:
    """GET /api/jobs — all active/queued jobs on all nodes, with created_at."""
    try:
        return await _get(_url("/api/jobs"), params={"timeout": timeout})
    except Exception as e:
        return _err(e, "get_jobs")


# ════════════════════════════════════════════════════════════
#  CONFIG  (routers/config.py)
# ════════════════════════════════════════════════════════════

async def ping() -> dict:
    """GET /api/ping — health check of the GUI backend."""
    try:
        return await _get(_url("/api/ping"))
    except Exception as e:
        return _err(e, "ping")


async def get_nodes_info() -> dict:
    """GET /api/nodes-info — full nodes_info.json + runtime targets."""
    try:
        return await _get(_url("/api/nodes-info"))
    except Exception as e:
        return _err(e, "get_nodes_info")


async def save_nodes_info(nodes_info: dict) -> dict:
    """POST /api/save-nodes-info — overwrites nodes_info.json."""
    try:
        return await _post(_url("/api/save-nodes-info"), {"nodes_info": nodes_info})
    except Exception as e:
        return _err(e, "save_nodes_info")


async def get_applications() -> dict:
    """GET /api/applications — all pipelines (applications.json)."""
    try:
        return await _get(_url("/api/applications"))
    except Exception as e:
        return _err(e, "get_applications")


async def save_applications(applications: dict) -> dict:
    """POST /api/save-applications — overwrites applications.json with the full structure."""
    try:
        return await _post(_url("/api/save-applications"), {"applications": applications})
    except Exception as e:
        return _err(e, "save_applications")


async def get_inputs() -> dict:
    """GET /api/inputs — content of inputs.json (raw text + parsed JSON)."""
    try:
        return await _get(_url("/api/inputs"))
    except Exception as e:
        return _err(e, "get_inputs")


async def save_inputs(raw_text: str) -> dict:
    """POST /api/save-inputs — saves inputs.json as text (must be valid JSON)."""
    try:
        return await _post(_url("/api/save-inputs"), {"raw_text": raw_text})
    except Exception as e:
        return _err(e, "save_inputs")


# ════════════════════════════════════════════════════════════
#  LOGS  (routers/recording.py)
# ════════════════════════════════════════════════════════════

async def get_logs(limit: int = 50) -> dict:
    """GET /api/logs — last N logs collected by the orchestrator."""
    try:
        return await _get(_url("/api/logs"), params={"limit": limit})
    except Exception as e:
        return _err(e, "get_logs")


async def clear_logs(node_id: str | None = None) -> dict:
    """POST /api/clear-logs — clears the logs (all nodes or a specific one)."""
    try:
        return await _post(_url("/api/clear-logs"), {"node_id": node_id})
    except Exception as e:
        return _err(e, "clear_logs")


# ════════════════════════════════════════════════════════════
#  RECORDING — Metrics  (routers/recording.py)
# ════════════════════════════════════════════════════════════

async def start_metrics_recording(
    interval_seconds: float = 1.0,
    duration_seconds: int = 0,
) -> dict:
    """POST /api/start-metrics-recording — starts CPU/RAM recording to CSV."""
    try:
        return await _post(_url("/api/start-metrics-recording"), {
            "interval_seconds": interval_seconds,
            "duration_seconds": duration_seconds,
        })
    except Exception as e:
        return _err(e, "start_metrics_recording")


async def stop_metrics_recording() -> dict:
    """POST /api/stop-metrics-recording — stops the metrics recording."""
    try:
        return await _post(_url("/api/stop-metrics-recording"), {})
    except Exception as e:
        return _err(e, "stop_metrics_recording")


async def get_metrics_recording_status() -> dict:
    """GET /api/metrics-recording-status — status of the recording session."""
    try:
        return await _get(_url("/api/metrics-recording-status"))
    except Exception as e:
        return _err(e, "get_metrics_recording_status")


async def get_metrics_recording_list() -> dict:
    """GET /api/metrics-recording-list — list of recorded metrics CSV files."""
    try:
        return await _get(_url("/api/metrics-recording-list"))
    except Exception as e:
        return _err(e, "get_metrics_recording_list")


# ════════════════════════════════════════════════════════════
#  RECORDING — Performance  (routers/recording.py)
# ════════════════════════════════════════════════════════════

async def start_performance_recording(
    duration_seconds: int = 0,
    label_filter: str | None = None,
    label_filters: list[str] | None = None,
) -> dict:
    """POST /api/start-performance-recording — starts job timing recording."""
    try:
        payload: dict = {"duration_seconds": duration_seconds}
        if label_filters:
            payload["label_filters"] = label_filters
        elif label_filter:
            payload["label_filter"] = label_filter
        return await _post(_url("/api/start-performance-recording"), payload)
    except Exception as e:
        return _err(e, "start_performance_recording")


async def stop_performance_recording() -> dict:
    """POST /api/stop-performance-recording — stops the performance recording."""
    try:
        return await _post(_url("/api/stop-performance-recording"), {})
    except Exception as e:
        return _err(e, "stop_performance_recording")


async def get_performance_recording_status() -> dict:
    """GET /api/performance-recording-status — status of the performance recording session."""
    try:
        return await _get(_url("/api/performance-recording-status"))
    except Exception as e:
        return _err(e, "get_performance_recording_status")


async def get_performance_recordings_list() -> dict:
    """GET /api/performance-recordings-list — list of recorded performance CSV files."""
    try:
        return await _get(_url("/api/performance-recordings-list"))
    except Exception as e:
        return _err(e, "get_performance_recordings_list")


# ════════════════════════════════════════════════════════════
#  JOBS  (routers/jobs.py)
# ════════════════════════════════════════════════════════════

async def get_job_timeline(label: str, job_id: str, timeout: float = 10.0) -> dict:
    """GET /api/job-timeline — detailed timeline of a job with all its steps."""
    try:
        return await _get(_url("/api/job-timeline"), params={
            "label": label, "job_id": job_id, "timeout": timeout,
        })
    except Exception as e:
        return _err(e, "get_job_timeline")


async def get_job_results(label: str, timeout: float = 10.0) -> dict:
    """GET /api/job-results — output of all completed jobs of a pipeline."""
    try:
        return await _get(_url("/api/job-results"), params={"label": label, "timeout": timeout})
    except Exception as e:
        return _err(e, "get_job_results")


async def get_tg_deployments() -> dict:
    """GET /api/tg-deployments — map node → list of tracked TGs (tg_deployments.json)."""
    try:
        return await _get(_url("/api/tg-deployments"))
    except Exception as e:
        return _err(e, "get_tg_deployments")


async def get_pipeline_steps(label: str) -> dict:
    """GET /api/pipeline-steps — list of the steps of a pipeline with node_id and service_ref."""
    try:
        return await _get(_url("/api/pipeline-steps"), params={"label": label})
    except Exception as e:
        return _err(e, "get_pipeline_steps")


async def get_job_list(label: str, timeout: float = 10.0) -> dict:
    """GET /api/job-list — list of job_id and status for a pipeline (queries the last node)."""
    try:
        return await _get(_url("/api/job-list"), params={"label": label, "timeout": timeout})
    except Exception as e:
        return _err(e, "get_job_list")


async def get_step_data(
    label: str, job_id: str, counter: int, node_id: str, timeout: float = 10.0
) -> dict:
    """GET /api/step-data — JSON input and output of a specific step on a node."""
    try:
        return await _get(_url("/api/step-data"), params={
            "label": label, "job_id": job_id,
            "counter": counter, "node_id": node_id, "timeout": timeout,
        })
    except Exception as e:
        return _err(e, "get_step_data")


async def launch_job() -> dict:
    """POST /api/launch — manually launches a job with the current inputs.json."""
    try:
        return await _post(_url("/api/launch"), {})
    except Exception as e:
        return _err(e, "launch_job")


# ════════════════════════════════════════════════════════════
#  TRAFFIC GENERATORS  (routers/tg.py)
# ════════════════════════════════════════════════════════════

async def get_tg_list_local() -> dict:
    """GET /api/traffic-generator-list-local — TGs available locally on the orchestrator."""
    try:
        return await _get(_url("/api/traffic-generator-list-local"))
    except Exception as e:
        return _err(e, "get_tg_list_local")


async def deploy_traffic_generator(
    tg_ref: str, nodes: list[str] | None = None
) -> dict:
    """POST /api/deploy-traffic-generator — copies the TG to the nodes via SSH."""
    try:
        payload: dict = {"tg_ref": tg_ref}
        if nodes:
            payload["nodes"] = nodes
        return await _post(_url("/api/deploy-traffic-generator"), payload)
    except Exception as e:
        return _err(e, "deploy_traffic_generator")


async def start_traffic_generator(
    node_id: str, label: str, tg_ref: str,
    iterations: int = -1, interval: float = 1.0,
) -> dict:
    """POST /api/start-traffic-generator — starts the TG on a node's runtime."""
    try:
        return await _post(_url("/api/start-traffic-generator"), {
            "node_id": node_id, "label": label, "tg_ref": tg_ref,
            "iterations": iterations, "interval": interval,
        })
    except Exception as e:
        return _err(e, "start_traffic_generator")


async def stop_traffic_generator(node_id: str, label: str) -> dict:
    """POST /api/stop-traffic-generator — stops the TG on a node."""
    try:
        return await _post(_url("/api/stop-traffic-generator"), {
            "node_id": node_id, "label": label,
        })
    except Exception as e:
        return _err(e, "stop_traffic_generator")


async def get_traffic_generator_status(label: str | None = None) -> dict:
    """GET /api/traffic-generator-status — TG status on all nodes (optional label filter)."""
    try:
        params = {"label": label} if label else {}
        return await _get(_url("/api/traffic-generator-status"), params=params)
    except Exception as e:
        return _err(e, "get_traffic_generator_status")


async def get_traffic_generator_list(nodes: list[str] | None = None) -> dict:
    """GET /api/traffic-generator-list — TGs available on the node runtimes."""
    try:
        params = {"nodes": nodes} if nodes else {}
        return await _get(_url("/api/traffic-generator-list"), params=params)
    except Exception as e:
        return _err(e, "get_traffic_generator_list")


# ════════════════════════════════════════════════════════════
#  FULL SYNC  (routers/full_sync.py)
# ════════════════════════════════════════════════════════════

async def full_sync(
    nodes: list[str] | None = None,
    ops: list[str] | None = None,
) -> dict:
    """POST /api/full-sync — full sync (services/applications/node_config/runtime_code/tg)."""
    try:
        payload: dict = {}
        if nodes:
            payload["nodes"] = nodes
        if ops:
            payload["ops"] = ops
        return await _post(_url("/api/full-sync"), payload)
    except Exception as e:
        return _err(e, "full_sync")


# ════════════════════════════════════════════════════════════
#  DEPLOY  (routers/deploy.py)
# ════════════════════════════════════════════════════════════

async def deploy_service_assets(nodes: list[str] | None = None) -> dict:
    """POST /api/deploy-service-assets — syncs the services/ directory to the nodes."""
    try:
        payload = {"nodes": nodes} if nodes else {}
        return await _post(_url("/api/deploy-service-assets"), payload)
    except Exception as e:
        return _err(e, "deploy_service_assets")


async def build_service_images(nodes: list[str] | None = None) -> dict:
    """POST /api/build-service-images — runs docker build for the services in docker mode."""
    try:
        payload = {"nodes": nodes} if nodes else {}
        return await _post(_url("/api/build-service-images"), payload)
    except Exception as e:
        return _err(e, "build_service_images")


async def configure_service(
    service_name: str,
    mode: str,
    nodes: list[str] | None = None,
    image: str | None = None,
    file_name: str | None = None,
    command: list[str] | None = None,
) -> dict:
    """POST /api/configure-service — adds/updates a service in the nodes_info service_catalog."""
    try:
        payload: dict = {"service_name": service_name, "mode": mode}
        if nodes:
            payload["nodes"] = nodes
        if image:
            payload["image"] = image
        if file_name:
            payload["file_name"] = file_name
        if command:
            payload["command"] = command
        return await _post(_url("/api/configure-service"), payload)
    except Exception as e:
        return _err(e, "configure_service")


async def delete_service(
    service_name: str,
    nodes: list[str] | None = None,
    mode: str | None = None,
    delete_files: bool = False,
) -> dict:
    """POST /api/delete-service — removes a service from the catalog (optionally also the local files)."""
    try:
        payload: dict = {"service_name": service_name, "delete_files": delete_files}
        if nodes:
            payload["nodes"] = nodes
        if mode:
            payload["mode"] = mode
        return await _post(_url("/api/delete-service"), payload)
    except Exception as e:
        return _err(e, "delete_service")


async def delete_application(application_name: str) -> dict:
    """POST /api/delete-application — deletes a pipeline from applications.json."""
    try:
        return await _post(_url("/api/delete-application"), {"application_name": application_name})
    except Exception as e:
        return _err(e, "delete_application")


async def delete_traffic_generator(
    tg_ref: str,
    node_ids: list[str] | None = None,
    delete_files: bool = False,
) -> dict:
    """POST /api/delete-traffic-generator — removes the TG from tracking (optionally also the files)."""
    try:
        payload: dict = {"tg_ref": tg_ref, "delete_files": delete_files}
        if node_ids:
            payload["node_ids"] = node_ids
        return await _post(_url("/api/delete-traffic-generator"), payload)
    except Exception as e:
        return _err(e, "delete_traffic_generator")


async def get_service_list() -> dict:
    """GET /api/service-list — services available locally in services/."""
    try:
        return await _get(_url("/api/service-list"))
    except Exception as e:
        return _err(e, "get_service_list")


async def deploy_service(
    service_name: str,
    mode: str,
    nodes: list[str] | None = None,
    image: str | None = None,
    file_name: str | None = None,
    command: list[str] | None = None,
    restart_api: bool = False,
) -> dict:
    """POST /api/deploy-service — distributes a service (files + catalog) to the nodes via SSH."""
    try:
        payload: dict = {"service_name": service_name, "mode": mode, "restart_api": restart_api}
        if nodes:
            payload["nodes"] = nodes
        if image:
            payload["image"] = image
        if file_name:
            payload["file_name"] = file_name
        if command:
            payload["command"] = command
        return await _post(_url("/api/deploy-service"), payload)
    except Exception as e:
        return _err(e, "deploy_service")


async def deploy_all_services(
    nodes: list[str] | None = None, restart_api: bool = False
) -> dict:
    """POST /api/deploy-all-services — distributes all local services to all nodes."""
    try:
        payload: dict = {"restart_api": restart_api}
        if nodes:
            payload["nodes"] = nodes
        return await _post(_url("/api/deploy-all-services"), payload)
    except Exception as e:
        return _err(e, "deploy_all_services")


async def sync_service_catalogs(nodes: list[str] | None = None) -> dict:
    """POST /api/sync-service-catalogs — reads the remote catalogs and updates nodes_info.json."""
    try:
        payload = {"nodes": nodes} if nodes else {}
        return await _post(_url("/api/sync-service-catalogs"), payload)
    except Exception as e:
        return _err(e, "sync_service_catalogs")


async def sync_services(
    nodes: list[str] | None = None, restart_api: bool = False
) -> dict:
    """POST /api/sync-services — syncs services/ + service_catalog.json to the nodes."""
    try:
        payload: dict = {"restart_api": restart_api}
        if nodes:
            payload["nodes"] = nodes
        return await _post(_url("/api/sync-services"), payload)
    except Exception as e:
        return _err(e, "sync_services")


async def deploy_plan_files(
    nodes: list[str] | None = None, restart_api: bool = True
) -> dict:
    """POST /api/deploy-plan-files — distributes application_plan.json to all nodes."""
    try:
        payload: dict = {"restart_api": restart_api}
        if nodes:
            payload["nodes"] = nodes
        return await _post(_url("/api/deploy-plan-files"), payload)
    except Exception as e:
        return _err(e, "deploy_plan_files")


async def deploy_plan_files_for_application(
    application_name: str, restart_api: bool = False
) -> dict:
    """POST /api/deploy-plan-files-for-application — distributes the plan files of a specific app."""
    try:
        return await _post(_url("/api/deploy-plan-files-for-application"), {
            "application_name": application_name,
            "restart_api": restart_api,
        })
    except Exception as e:
        return _err(e, "deploy_plan_files_for_application")


async def sync_clock(nodes: list[str] | None = None) -> dict:
    """POST /api/sync-clock — syncs NTP on the nodes (ntpdate/chrony/timedatectl)."""
    try:
        payload = {"nodes": nodes} if nodes else {}
        return await _post(_url("/api/sync-clock"), payload)
    except Exception as e:
        return _err(e, "sync_clock")


async def restart_runtime(nodes: list[str] | None = None) -> dict:
    """POST /api/restart-runtime — restarts mosaic-runtime.service on the nodes."""
    try:
        payload = {"nodes": nodes} if nodes else {}
        return await _post(_url("/api/restart-runtime"), payload)
    except Exception as e:
        return _err(e, "restart_runtime")


async def check_sync(nodes: list[str] | None = None) -> dict:
    """POST /api/check-sync — checks whether the nodes are aligned with the local configuration."""
    try:
        payload = {"nodes": nodes} if nodes else {}
        return await _post(_url("/api/check-sync"), payload)
    except Exception as e:
        return _err(e, "check_sync")


async def deploy_node_configs(nodes: list[str] | None = None) -> dict:
    """POST /api/deploy-node-configs — generates and distributes node_config.json to the nodes."""
    try:
        payload = {"nodes": nodes} if nodes else {}
        return await _post(_url("/api/deploy-node-configs"), payload)
    except Exception as e:
        return _err(e, "deploy_node_configs")


async def deploy_runtime_code(
    nodes: list[str] | None = None, restart_api: bool = True
) -> dict:
    """POST /api/deploy-runtime-code — distributes the runtime code (runtime_code/) to the nodes."""
    try:
        payload: dict = {"restart_api": restart_api}
        if nodes:
            payload["nodes"] = nodes
        return await _post(_url("/api/deploy-runtime-code"), payload)
    except Exception as e:
        return _err(e, "deploy_runtime_code")


async def install_node(node_id: str, post_install_delay: float = 3.0) -> dict:
    """POST /api/install-node — installs MOSAIC on a node via SSH (install_node.sh)."""
    try:
        return await _post(_url("/api/install-node"), {
            "node_id": node_id,
            "post_install_delay": post_install_delay,
        })
    except Exception as e:
        return _err(e, "install_node")


async def uninstall_node(node_id: str) -> dict:
    """POST /api/uninstall-node — removes MOSAIC from a node via SSH (uninstall_node.sh)."""
    try:
        return await _post(_url("/api/uninstall-node"), {"node_id": node_id})
    except Exception as e:
        return _err(e, "uninstall_node")
