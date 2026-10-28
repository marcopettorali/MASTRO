"""
MCP tools — Placement and pipeline configuration.
Covers: GET/POST /api/applications, POST /api/save-applications,
        POST /api/delete-application, POST /api/deploy-plan-files,
        POST /api/deploy-plan-files-for-application.
These tools modify the MOSAIC Scenario Configuration.
"""

import logging

from fastmcp import FastMCP

from ..config import cfg
from ..clients import orchestrator as orch
from ..mock.data import MOCK_APPLICATIONS

logger = logging.getLogger("mastro.mcp_gateway.tools.placement")


def _apps_map(result: dict, app_name: str | None = None) -> dict:
    """Return the {app_name: definition} map from a GET /api/applications result.

    The backend's GET wraps the whole applications.json (whose top-level key is
    already "applications") under another "applications" key, so the raw result
    is {"ok":..., "applications": {"applications": {<name>: {...}}}}. This helper
    tolerates both the single- and double-wrapped shapes.
    """
    apps = result.get("applications", {})
    if not isinstance(apps, dict):
        return {}
    inner = apps.get("applications")
    if isinstance(inner, dict) and (app_name is None or app_name not in apps):
        return inner
    return apps


def register(mcp: FastMCP) -> None:

    # ── GET /api/applications ─────────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_get_applications() -> dict:
        """
        All the pipelines (applications) defined in MOSAIC with their steps,
        execution nodes, service_ref and forward nodes.
        Call it before any placement operation.
        """
        if cfg.mock_mode:
            return MOCK_APPLICATIONS
        return await orch.get_applications()

    @mcp.tool()
    async def mosaic_get_application_steps(app_name: str) -> dict:
        """
        Steps of a specific pipeline with the current deployment
        (which node runs which step).

        Args:
            app_name: application name (e.g. "inference_pipeline")
        """
        if cfg.mock_mode:
            apps = MOCK_APPLICATIONS.get("applications", {})
            if app_name not in apps:
                return {"error": True, "detail": f"Application '{app_name}' not found"}
            return {"ok": True, app_name: apps[app_name]}

        result = await orch.get_applications()
        if "error" in result:
            return result
        apps = _apps_map(result, app_name)
        if app_name not in apps:
            return {"error": True, "detail": f"Application '{app_name}' not found"}
        return {"ok": True, app_name: apps[app_name]}

    # ── mosaic_set_placement — high-level shortcut ────────────────────────────

    @mcp.tool()
    async def mosaic_set_placement(
        app_name: str,
        step_assignments: list[dict],
        reason: str,
        restart_runtime: bool = False,
        rewire_chain: bool = True,
    ) -> dict:
        """
        Update the placement of one or more steps and propagate the configuration to the nodes.
        This is the main action of Tier 1 (optimization) and Tier 2 (service migration).

        step_assignments is a list of {counter: int, node_id: str}.
        Example: [{"counter": 2, "node_id": "fog2"}] moves step 2 to fog2.

        Internally: reads applications → updates node_id → (if rewire_chain)
        recomputes the chain's forward_to → POST /api/save-applications
        → POST /api/deploy-plan-files-for-application.

        With rewire_chain=True (default), after reassigning the node_ids the tool
        automatically rebuilds the forward_to of a LINEAR pipeline, so that
        each step forwards to the node hosting the next step (the last
        step has no forward). This is needed because migrating an intermediate
        step in a chain of 3+ services would otherwise break forwarding
        (forward_to would still point to the old node). If the pipeline is not
        linear, rewiring is skipped and a warning is returned.

        WARNING: irreversible until a new set_placement.

        Args:
            app_name: pipeline name
            step_assignments: list of {counter, node_id}
            reason: rationale (required for the reasoning log)
            restart_runtime: IGNORED (compat) — a placement change always uses hot-reload,
                never a hard restart of the runtime (which would break the running pipeline)
            rewire_chain: if True (default) recompute forward_to for linear chains
        """
        if cfg.dry_run:
            logger.info("[DRY-RUN] set_placement: %s -> %s | %s", app_name, step_assignments, reason)
            return {
                "dry_run": True,
                "app_name": app_name,
                "step_assignments": step_assignments,
                "reason": reason,
                "message": "Dry-run: no changes applied",
            }

        if cfg.mock_mode:
            return {
                "success": True,
                "app_name": app_name,
                "updated_steps": step_assignments,
                "deployed_to_nodes": ["fog1", "fog2", "server"],
                "reason": reason,
            }

        # 1. Read the current configuration
        result = await orch.get_applications()
        if "error" in result:
            return result
        apps = _apps_map(result, app_name)
        if app_name not in apps:
            return {"error": True, "detail": f"Application '{app_name}' not found"}

        # 2. Apply the changes to the steps
        steps = apps[app_name].get("steps", [])
        assignment_map = {a["counter"]: a["node_id"] for a in step_assignments}
        for step in steps:
            c = step.get("counter")
            if c in assignment_map:
                step["node_id"] = assignment_map[c]

        # 2b. Rewire forward_to for a linear chain (see docstring).
        rewired = False
        rewire_warning = None
        if rewire_chain and isinstance(steps, list) and steps:
            counters = [s.get("counter") for s in steps]
            is_linear = (
                all(isinstance(c, int) for c in counters)
                and len(set(counters)) == len(counters)
                and sorted(counters) == list(range(min(counters), max(counters) + 1))
            )
            if is_linear:
                ordered = sorted(steps, key=lambda s: s["counter"])
                for i, step in enumerate(ordered):
                    if i < len(ordered) - 1:
                        step["forward_to"] = [{"node_id": ordered[i + 1]["node_id"]}]
                    else:
                        step["forward_to"] = []
                rewired = True
            else:
                rewire_warning = (
                    "Non-linear pipeline: forward_to was not recomputed automatically. "
                    "Check the forwarding manually after the migration."
                )

        # 3. Save the updated configuration (POST /api/save-applications)
        apps[app_name]["steps"] = steps
        save_result = await orch.save_applications({"applications": apps})
        if "error" in save_result:
            return save_result

        deploy_result = await orch.deploy_plan_files_for_application(
            application_name=app_name,
            restart_api=False,
        )

        logger.info("set_placement OK: %s steps=%s reason=%s rewired=%s",
                    app_name, step_assignments, reason, rewired)
        result_payload = {
            "success": True,
            "app_name": app_name,
            "updated_steps": step_assignments,
            "forward_to_rewired": rewired,
            "deploy_result": deploy_result,
            "reason": reason,
        }
        if rewire_warning:
            result_payload["warning"] = rewire_warning
        return result_payload

    # ── POST /api/save-applications ───────────────────────────────────────────

    @mcp.tool()
    async def mosaic_save_applications(applications: dict) -> dict:
        """
        Completely overwrite applications.json with the given structure.
        Use mosaic_set_placement for partial placement changes;
        use this one for structural changes to the pipeline.

        The payload must have the form {"applications": {"pipeline_name": {...}}}.

        Args:
            applications: full structure {"applications": {name: {steps: [...]}}}
        """
        if cfg.mock_mode:
            return {"ok": True, "message": "applications.json saved (mock)"}
        return await orch.save_applications(applications)

    # ── POST /api/delete-application ──────────────────────────────────────────

    @mcp.tool()
    async def mosaic_delete_application(application_name: str) -> dict:
        """
        Delete a pipeline from applications.json. Irreversible operation.
        After deletion, run an applications sync to propagate it to the nodes.

        Args:
            application_name: name of the pipeline to delete
        """
        if cfg.mock_mode:
            return {"ok": True, "application_name": application_name, "sync_required": True}
        return await orch.delete_application(application_name)

    # ── POST /api/deploy-plan-files-for-application ───────────────────────────

    @mcp.tool()
    async def mosaic_deploy_plan_files_for_application(
        application_name: str,
        restart_runtime: bool = False,
    ) -> dict:
        """
        Distribute the application_plan.json files of a specific pipeline
        to the nodes that belong to it. Use it after saving with mosaic_save_applications
        or to force a re-sync of a single pipeline.

        Args:
            application_name: pipeline name
            restart_runtime: if True restart the runtime on the nodes after the deploy
        """
        if cfg.mock_mode:
            return {"ok": True, "application_name": application_name}
        return await orch.deploy_plan_files_for_application(
            application_name=application_name,
            restart_api=restart_runtime,
        )

    # ── POST /api/deploy-plan-files ───────────────────────────────────────────

    @mcp.tool()
    async def mosaic_deploy_plan_files(
        nodes: list[str] | None = None,
        restart_runtime: bool = True,
    ) -> dict:
        """
        Distribute application_plan.json of ALL pipelines
        to all nodes (or only the given ones).

        Args:
            nodes: list of target nodes (None = all)
            restart_runtime: if True restart the runtime after the deploy (default True)
        """
        if cfg.mock_mode:
            return {"ok": True, "nodes": nodes or ["fog1", "fog2", "server"]}
        return await orch.deploy_plan_files(nodes=nodes, restart_api=restart_runtime)

    # ── GET /api/pipeline-steps ───────────────────────────────────────────────

    @mcp.tool()
    async def mosaic_get_pipeline_steps(label: str) -> dict:
        """
        List of the steps of a pipeline with counter, node_id, service_ref,
        forward_to. Fast read from applications.json without querying the nodes.

        Args:
            label: pipeline name (e.g. "inference_pipeline")
        """
        if cfg.mock_mode:
            apps = MOCK_APPLICATIONS.get("applications", {})
            pipeline = apps.get(label)
            if not pipeline:
                return {"error": True, "detail": f"Application '{label}' not found"}
            return {"ok": True, "label": label, "steps": pipeline.get("steps", [])}
        return await orch.get_pipeline_steps(label=label)
