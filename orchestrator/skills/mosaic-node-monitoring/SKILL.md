---
name: mosaic-node-monitoring
description: Domain knowledge for monitoring MOSAIC node health, metrics and status. Use when the operator asks about node performance, resource usage, CPU, RAM, or system health.
---

# MOSAIC Node Monitoring

## Overview
MOSAIC nodes expose real-time metrics via the orchestrator. Each node reports:
- **CPU usage** (percentage 0-100)
- **RAM usage** (used / free / total in bytes)
- **Status**: `online`, `offline`, `unknown`

## Key tools to use

| Goal | Tool |
|---|---|
| Quick system overview | `mosaic_get_system_status` |
| All node metrics at once | `mosaic_get_all_metrics` |
| Single node deep dive | `mosaic_get_node_metrics` + `mosaic_get_node_status` |
| Node connectivity check | `mosaic_ping` + `mosaic_check_node_health` |

## Reasoning guidelines

1. **Start broad**: always call `mosaic_get_system_status` first to understand which nodes are online.
2. **Prioritize anomalies**: if CPU > 85% or RAM free < 15%, flag it explicitly.
3. **Context matters**: a spike during active job execution is normal; the same spike at idle is concerning.
4. **RAM calculation**: available RAM = `free` field (not `total - used`, which may differ due to OS caching).
5. **Offline nodes**: if a node is offline, do not attempt to read its runtime metrics — report it as unreachable.

## Interpretation thresholds (reference)

| Metric | Normal | Warning | Critical |
|---|---|---|---|
| CPU % | < 70 | 70–85 | > 85 |
| RAM free | > 20% total | 10–20% | < 10% |
| Node status | online | - | offline |

## Response format
When reporting node health, structure your answer as:
1. Overall system health (X/Y nodes online)
2. Per-node summary (only flag deviations from normal)
3. Recommendations if any thresholds are exceeded
