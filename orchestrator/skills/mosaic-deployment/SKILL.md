---
name: mosaic-deployment
description: Knowledge for managing MOSAIC service deployments, syncing code, and managing node lifecycle. Use when the operator asks about deploying services, syncing nodes, or applying configuration changes.
---

# MOSAIC Deployment

## Overview
MOSAIC pushes service code and configuration to runtime nodes via SSH.
The deployment workflow is:
1. **Configure** service placement in applications.json
2. **Generate** node-specific plan files (`mosaic_deploy_plan_files`)
3. **Deploy** service code to nodes (`mosaic_deploy_service` or `mosaic_deploy_all_services`)
4. **Restart** runtime API if needed

## Key tools

| Goal | Tool |
|---|---|
| Deploy all services | `mosaic_deploy_all_services` |
| Deploy single service | `mosaic_deploy_service` |
| Sync runtime code | `mosaic_deploy_runtime_code` |
| Push plan files | `mosaic_deploy_plan_files` |
| Check sync state | `mosaic_check_sync` |
| Full sync (all steps) | `mosaic_full_sync` |
| Restart runtime | `mosaic_restart_runtime` |

## Safety guidelines

1. **Always check sync first**: call `mosaic_check_sync` before deploying to understand what needs updating.
2. **Dry run awareness**: if DRY_RUN is enabled, write operations are logged but not executed.
3. **Restart impact**: `restart_api: true` restarts the runtime service on the node — active jobs will be interrupted.
4. **Node selection**: most deploy tools accept a `nodes` list; `null` means all configured nodes.

## Deployment sequence (typical)
1. `mosaic_check_sync` → identify out-of-sync nodes
2. `mosaic_deploy_plan_files` → push placement config
3. `mosaic_deploy_all_services` → push service code
4. Optionally: `mosaic_restart_runtime` if a full restart is needed
