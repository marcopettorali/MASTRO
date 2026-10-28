"""
MCP tools — Deploy and Sync: distribution of services, plan files, node configuration,
            runtime code, traffic generators, full sync, install/uninstall.
Covers: routers/deploy.py + routers/full_sync.py.
All tools with side effects on remote nodes honour DRY_RUN.
"""

import logging

from fastmcp import FastMCP

from ..config import cfg
from ..clients import orchestrator as orch

logger = logging.getLogger("mastro.mcp_gateway.tools.deploy")

_DRY = lambda name: {"dry_run": True, "message": f"{name}: no changes applied"}


def register(mcp: FastMCP) -> None:

    # ════════════════════════════════════════════════════════
    #  SERVICE — Local management  (routers/deploy.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_get_service_list() -> dict:
        """
        List of the services available locally in the services/ directory,
        with their modes (local/docker) and the files they contain.
        """
        if cfg.mock_mode:
            return {"ok": True, "services": {"inference_service": {"local": {"files": ["main.py"]}}}}
        return await orch.get_service_list()

    @mcp.tool()
    async def mosaic_configure_service(
        service_name: str,
        mode: str,
        nodes: list[str] | None = None,
        image: str | None = None,
        file_name: str | None = None,
        command: list[str] | None = None,
    ) -> dict:
        """
        Add or update a service in the service_catalog of nodes_info.json.
        Does NOT distribute the service to the nodes — use mosaic_deploy_service for that.

        Args:
            service_name: service name
            mode: "local" or "docker"
            nodes: nodes the configuration applies to (None = all)
            image: Docker image (required if mode="docker")
            file_name: main file for mode="local" (default "main.py")
            command: start command for mode="local" (default ["python3", file_name])
        """
        if cfg.dry_run:
            return _DRY("configure_service")
        if cfg.mock_mode:
            return {"ok": True, "service_name": service_name, "mode": mode}
        return await orch.configure_service(
            service_name=service_name, mode=mode, nodes=nodes,
            image=image, file_name=file_name, command=command,
        )

    @mcp.tool()
    async def mosaic_delete_service(
        service_name: str,
        nodes: list[str] | None = None,
        mode: str | None = None,
        delete_files: bool = False,
    ) -> dict:
        """
        Remove a service from the service_catalog of nodes_info.json.
        Run mosaic_sync_services afterwards to propagate the removal to the nodes.

        Args:
            service_name: name of the service to remove
            nodes: nodes to remove it from (None = all)
            mode: remove only the given mode (None = both)
            delete_files: if True also delete the local files in services/
        """
        if cfg.dry_run:
            return _DRY("delete_service")
        if cfg.mock_mode:
            return {"ok": True, "service_name": service_name, "sync_required": True}
        return await orch.delete_service(
            service_name=service_name, nodes=nodes, mode=mode, delete_files=delete_files,
        )

    @mcp.tool()
    async def mosaic_deploy_service(
        service_name: str,
        mode: str,
        nodes: list[str] | None = None,
        image: str | None = None,
        file_name: str | None = None,
        command: list[str] | None = None,
        restart_api: bool = False,
    ) -> dict:
        """
        Distribute a service (files + service_catalog update) to the nodes via SSH.
        The files must already be present locally in services/{service_name}/{mode}/.

        Args:
            service_name: service name
            mode: "local" or "docker"
            nodes: target nodes (None = all)
            image: Docker image (required if mode="docker")
            file_name: main file (default "main.py")
            command: start command (default ["python3", file_name])
            restart_api: if True restart the runtime after the deploy
        """
        if cfg.dry_run:
            return _DRY("deploy_service")
        if cfg.mock_mode:
            return {"ok": True, "action": "deploy_service", "service_name": service_name}
        return await orch.deploy_service(
            service_name=service_name, mode=mode, nodes=nodes,
            image=image, file_name=file_name, command=command, restart_api=restart_api,
        )

    @mcp.tool()
    async def mosaic_deploy_all_services(
        nodes: list[str] | None = None,
        restart_api: bool = False,
    ) -> dict:
        """
        Distribute all local services to all nodes (incremental sync).

        Args:
            nodes: target nodes (None = all)
            restart_api: if True restart the runtime after the deploy
        """
        if cfg.dry_run:
            return _DRY("deploy_all_services")
        if cfg.mock_mode:
            return {"ok": True, "action": "deploy_all_services"}
        return await orch.deploy_all_services(nodes=nodes, restart_api=restart_api)

    @mcp.tool()
    async def mosaic_deploy_service_assets(nodes: list[str] | None = None) -> dict:
        """
        Synchronize the services/ directory to the nodes without updating the service_catalog.
        Useful to update the files of an already configured service.

        Args:
            nodes: target nodes (None = all)
        """
        if cfg.dry_run:
            return _DRY("deploy_service_assets")
        if cfg.mock_mode:
            return {"ok": True, "action": "deploy_service_assets"}
        return await orch.deploy_service_assets(nodes=nodes)

    @mcp.tool()
    async def mosaic_build_service_images(nodes: list[str] | None = None) -> dict:
        """
        Run docker build on the nodes for the services in docker mode.
        Nodes without docker services are skipped automatically.

        Args:
            nodes: target nodes (None = all)
        """
        if cfg.dry_run:
            return _DRY("build_service_images")
        if cfg.mock_mode:
            return {"ok": True, "action": "build_service_images"}
        return await orch.build_service_images(nodes=nodes)

    # ════════════════════════════════════════════════════════
    #  SERVICE CATALOG SYNC
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_sync_service_catalogs(nodes: list[str] | None = None) -> dict:
        """
        Read the service_catalog.json files from the remote nodes and update nodes_info.json.
        Use it to align the local configuration with the actual state of the nodes.

        Args:
            nodes: nodes to synchronize (None = all)
        """
        if cfg.dry_run:
            return _DRY("sync_service_catalogs")
        if cfg.mock_mode:
            return {"ok": True, "action": "sync_service_catalogs"}
        return await orch.sync_service_catalogs(nodes=nodes)

    @mcp.tool()
    async def mosaic_sync_services(
        nodes: list[str] | None = None,
        restart_api: bool = False,
    ) -> dict:
        """
        Distribute services/ + service_catalog.json to the nodes (incremental sync).
        Equivalent to mosaic_deploy_service_assets + catalog update.

        Args:
            nodes: target nodes (None = all)
            restart_api: if True restart the runtime after the sync
        """
        if cfg.dry_run:
            return _DRY("sync_services")
        if cfg.mock_mode:
            return {"ok": True, "action": "sync_services"}
        return await orch.sync_services(nodes=nodes, restart_api=restart_api)

    # ════════════════════════════════════════════════════════
    #  TRAFFIC GENERATOR — Deploy  (routers/tg.py + deploy.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_deploy_traffic_generator(
        tg_ref: str,
        nodes: list[str] | None = None,
    ) -> dict:
        """
        Copy the traffic generator to the nodes via SSH and update tg_deployments.json.
        The TG must already be present locally (traffic_generators/{tg_ref}/).

        Args:
            tg_ref: traffic generator name
            nodes: target nodes (None = all)
        """
        if cfg.dry_run:
            return _DRY("deploy_traffic_generator")
        if cfg.mock_mode:
            return {"ok": True, "tg_ref": tg_ref, "nodes": nodes}
        return await orch.deploy_traffic_generator(tg_ref=tg_ref, nodes=nodes)

    @mcp.tool()
    async def mosaic_delete_traffic_generator(
        tg_ref: str,
        node_ids: list[str] | None = None,
        delete_files: bool = False,
    ) -> dict:
        """
        Remove the traffic generator from tracking (tg_deployments.json).
        Run a TG sync to physically remove it from the nodes.

        Args:
            tg_ref: traffic generator name
            node_ids: nodes to remove it from (None = all)
            delete_files: if True also delete the local files
        """
        if cfg.dry_run:
            return _DRY("delete_traffic_generator")
        if cfg.mock_mode:
            return {"ok": True, "tg_ref": tg_ref, "sync_required": True}
        return await orch.delete_traffic_generator(
            tg_ref=tg_ref, node_ids=node_ids, delete_files=delete_files,
        )

    # ════════════════════════════════════════════════════════
    #  NODE CONFIG & RUNTIME CODE  (routers/deploy.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_deploy_node_configs(nodes: list[str] | None = None) -> dict:
        """
        Generate and distribute node_config.json to the nodes.
        Required after changes to nodes_info.json that affect the topology.

        Args:
            nodes: target nodes (None = all)
        """
        if cfg.dry_run:
            return _DRY("deploy_node_configs")
        if cfg.mock_mode:
            return {"ok": True, "action": "deploy_node_configs"}
        return await orch.deploy_node_configs(nodes=nodes)

    @mcp.tool()
    async def mosaic_deploy_runtime_code(
        nodes: list[str] | None = None,
        restart_api: bool = True,
    ) -> dict:
        """
        Distribute the runtime code (runtime_code/) to the nodes (incremental sync).
        Use it to update the runtime without a full reinstall.

        Args:
            nodes: target nodes (None = all)
            restart_api: if True restart the runtime after the deploy (default True)
        """
        if cfg.dry_run:
            return _DRY("deploy_runtime_code")
        if cfg.mock_mode:
            return {"ok": True, "action": "deploy_runtime_code"}
        return await orch.deploy_runtime_code(nodes=nodes, restart_api=restart_api)

    # ════════════════════════════════════════════════════════
    #  SYNC OPERATIONS  (routers/deploy.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_sync_clock(nodes: list[str] | None = None) -> dict:
        """
        Synchronize the NTP clock on the nodes (ntpdate / chrony / timedatectl).
        Essential for correct timings in the performance logs.

        Args:
            nodes: nodes to synchronize (None = all)
        """
        if cfg.dry_run:
            return _DRY("sync_clock")
        if cfg.mock_mode:
            return {"ok": True, "action": "sync_clock"}
        return await orch.sync_clock(nodes=nodes)

    @mcp.tool()
    async def mosaic_restart_runtime(nodes: list[str] | None = None) -> dict:
        """
        Restart mosaic-runtime.service on the nodes via SSH.
        Required to apply changes to the runtime configuration.

        Args:
            nodes: target nodes (None = all)
        """
        if cfg.dry_run:
            return _DRY("restart_runtime")
        if cfg.mock_mode:
            return {"ok": True, "action": "restart_runtime"}
        return await orch.restart_runtime(nodes=nodes)

    @mcp.tool()
    async def mosaic_check_sync(nodes: list[str] | None = None) -> dict:
        """
        Check whether the nodes are aligned with the local configuration
        (node_config.json, service_catalog.json, application_plan.json).

        Args:
            nodes: nodes to check (None = all)
        """
        if cfg.mock_mode:
            return {"ok": True, "result": {"fog1": {"in_sync": True}, "fog2": {"in_sync": True}}}
        return await orch.check_sync(nodes=nodes)

    # ════════════════════════════════════════════════════════
    #  FULL SYNC  (routers/full_sync.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_full_sync(
        nodes: list[str] | None = None,
        ops: list[str] | None = None,
    ) -> dict:
        """
        Full sync: distributes services, applications, node_config,
        runtime_code and traffic_generators in parallel to all nodes.
        ops filters the operations to run (default: all 5).
        Valid values for ops: "services", "applications", "node_config",
        "runtime_code", "traffic_generators".

        Args:
            nodes: target nodes (None = all)
            ops: operations to run (None = all)
        """
        if cfg.dry_run:
            return _DRY("full_sync")
        if cfg.mock_mode:
            return {"ok": True, "action": "full_sync", "nodes": nodes}
        return await orch.full_sync(nodes=nodes, ops=ops)

    # ════════════════════════════════════════════════════════
    #  NODE INSTALL / UNINSTALL  (routers/deploy.py)
    # ════════════════════════════════════════════════════════

    @mcp.tool()
    async def mosaic_install_node(
        node_id: str,
        post_install_delay: float = 3.0,
    ) -> dict:
        """
        Install MOSAIC on a node via SSH by running install_node.sh.
        Requires the node to be configured in nodes_info.json with SSH credentials.

        Args:
            node_id: ID of the node to install
            post_install_delay: wait time in seconds after the installation (default 3.0)
        """
        if cfg.dry_run:
            return _DRY("install_node")
        if cfg.mock_mode:
            return {"ok": True, "node_id": node_id, "log": ["[mock] Installation complete"]}
        return await orch.install_node(node_id=node_id, post_install_delay=post_install_delay)

    @mcp.tool()
    async def mosaic_uninstall_node(node_id: str) -> dict:
        """
        Remove MOSAIC from a node via SSH by running uninstall_node.sh.

        Args:
            node_id: ID of the node to uninstall
        """
        if cfg.dry_run:
            return _DRY("uninstall_node")
        if cfg.mock_mode:
            return {"ok": True, "node_id": node_id, "log": ["[mock] Uninstallation complete"]}
        return await orch.uninstall_node(node_id=node_id)
