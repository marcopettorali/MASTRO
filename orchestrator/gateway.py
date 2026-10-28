"""MOSAIC MCP tools and instructions."""
import os
from .config import cfg
from .tools import monitoring, placement, ops, deploy

INSTRUCTIONS = """
You are the MASTRO MCP Gateway. You expose the state and the operations of the MOSAIC framework
to AI agents that control an edge datacenter.

MOSAIC is a pipeline orchestration system over heterogeneous nodes (edge/fog/cloud).
Every REST backend endpoint is mapped 1:1 to an MCP tool — the backend is never modified.

Available tools by category:

MONITORING (read-only, safe at high frequency):
  mosaic_ping, mosaic_get_system_status, mosaic_get_all_metrics, mosaic_get_all_jobs,
  mosaic_get_logs, mosaic_get_nodes_info,
  mosaic_get_node_metrics, mosaic_get_node_status, mosaic_get_node_info,
  mosaic_check_node_health, mosaic_get_all_nodes_status

PLACEMENT (modify the Scenario Configuration):
  mosaic_get_applications, mosaic_get_application_steps, mosaic_get_pipeline_steps,
  mosaic_set_placement, mosaic_save_applications, mosaic_delete_application,
  mosaic_deploy_plan_files_for_application, mosaic_deploy_plan_files

JOBS (job and step inspection):
  mosaic_get_job_list, mosaic_get_job_results, mosaic_get_job_timeline,
  mosaic_get_step_data, mosaic_launch_job, mosaic_get_tg_deployments,
  mosaic_list_node_jobs, mosaic_get_node_job, mosaic_get_node_job_steps,
  mosaic_get_node_step, mosaic_get_node_step_input, mosaic_get_node_step_output,
  mosaic_drain_node_logs

CONFIG (configuration read/write):
  mosaic_get_inputs, mosaic_save_inputs, mosaic_save_nodes_info

RECORDING (metrics and performance CSV sessions):
  mosaic_start_metrics_recording, mosaic_stop_metrics_recording,
  mosaic_get_metrics_recording_status, mosaic_get_metrics_recording_list,
  mosaic_start_performance_recording, mosaic_stop_performance_recording,
  mosaic_get_performance_recording_status, mosaic_get_performance_recordings_list,
  mosaic_clear_logs

TRAFFIC GENERATOR:
  mosaic_get_tg_list_local, mosaic_start_traffic_generator, mosaic_stop_traffic_generator,
  mosaic_get_traffic_generator_status, mosaic_get_traffic_generator_list

DEPLOY (distributes files to the nodes via SSH):
  mosaic_get_service_list, mosaic_configure_service, mosaic_delete_service,
  mosaic_deploy_service, mosaic_deploy_all_services, mosaic_deploy_service_assets,
  mosaic_build_service_images, mosaic_sync_service_catalogs, mosaic_sync_services,
  mosaic_deploy_traffic_generator, mosaic_delete_traffic_generator,
  mosaic_deploy_node_configs, mosaic_deploy_runtime_code,
  mosaic_sync_clock, mosaic_restart_runtime, mosaic_check_sync, mosaic_full_sync,
  mosaic_install_node, mosaic_uninstall_node

MCP AGENT MANAGEMENT (MCP process lifecycle):
  mastro_mcp_status, mastro_mcp_logs, mastro_mcp_nodes,
  mastro_mcp_start, mastro_mcp_stop

NOTE — The file-upload endpoints (/api/upload-inputs, /api/upload-service-files,
/api/upload-service-to-catalog, /api/upload-traffic-generator) require
multipart form-data and cannot be exposed via MCP. Use instead:
  - mosaic_save_inputs to update inputs.json as text
  - mosaic_deploy_service to distribute services already present locally

MOCK_MODE: """ + str(cfg.mock_mode) + """
DRY_RUN:   """ + str(cfg.dry_run) + """
Orchestrator: """ + cfg.orchestrator_base_url

def register_tools(mcp):
    modules = {"monitoring": monitoring, "placement": placement, "ops": ops, "deploy": deploy}
    selected = os.getenv("MASTRO_MCP_TOOLS", os.getenv("MOSAIC_MCP_TOOLS", "")).strip()
    names = [n.strip() for n in selected.split(",") if n.strip()] if selected else list(modules)
    for name in names:
        if name == "mcp_ctrl":
            continue  # Platform tools are registered by the generic gateway.
        if name not in modules:
            raise ValueError(f"Unknown adapter tool module: {name}")
        modules[name].register(mcp)
