---
name: mosaic-topology
description: Knowledge about MOSAIC datacenter topology, node roles, and service placement. Use when the operator asks about the cluster structure, service configuration, or application layout.
---

# MOSAIC Topology

## Overview
A MOSAIC deployment consists of:
- **Orchestrator node**: hosts the GUI backend and coordinates the cluster
- **Runtime nodes (fog/edge)**: execute service steps, expose metrics on a runtime port
- **Service catalog**: definitions of deployable services per node

## Key tools

| Goal | Tool |
|---|---|
| Full topology view | `mosaic_get_nodes_info` |
| Per-node runtime status | `mosaic_get_node_info` + `mosaic_get_all_nodes_status` |
| Application placement | `mosaic_get_applications` + `mosaic_get_application_steps` |
| Service list | `mosaic_get_service_list` |
| Pipeline step placement | `mosaic_get_pipeline_steps` |

## Reasoning guidelines

1. **Node identity**: each node has an ID (e.g. `fog-1`), a host IP, SSH credentials, and a runtime port.
2. **Placement**: `mosaic_get_applications` shows which services are assigned to which nodes in the current scenario.
3. **Service catalog**: `mosaic_get_service_list` shows locally available services that can be deployed.
4. **Config vs. runtime**: `mosaic_get_nodes_info` is the static config; `mosaic_get_all_nodes_status` is live runtime state.

## Common questions

- *"Which nodes are in the cluster?"* → `mosaic_get_nodes_info`
- *"Where is service X running?"* → `mosaic_get_applications` + filter
- *"What's deployed on node fog-1?"* → `mosaic_list_node_jobs` + `mosaic_get_node_info`
