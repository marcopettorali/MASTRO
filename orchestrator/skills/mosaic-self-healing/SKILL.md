---
name: mosaic-self-healing
description: Decision procedure for recovering a MOSAIC pipeline after a NODE FAILURE. Use when a node goes offline/unreachable and the pipeline steps it was hosting are interrupted; the agent must detect the failure and migrate the orphaned steps to the best surviving node.
---

# MOSAIC Self-Healing (node-failure recovery)

## Overview
This is failure recovery, NOT load rebalancing. A node can go offline
(crash, disconnect, runtime down). Any `audio_chain` step that was placed on
that node is now dead: jobs that reach it fail and the pipeline stops
completing work. The corrective action is to **migrate the orphaned steps off
the dead node onto the best surviving node**, which reconnects the chain.

## Detecting a failure
- `mosaic_get_system_status` / `mosaic_get_all_nodes_status`: a failed node is
  reported offline / not `ok` / unreachable. Treat a node as DOWN when its
  status is not ok (do not require CPU metrics — a dead node may report none).
- Cross-check with `mosaic_get_application_steps('audio_chain')`: if a step's
  `node_id` is a node that is now DOWN, that step is orphaned.

## Choosing the target node
Among the nodes that are still ONLINE (never the dead one, never a node that
already left the cluster):
1. Prefer the node with the most capacity — this cluster is heterogeneous
   (node01 = 1 vCPU, node02 = 2 vCPU, node03 = 4 vCPU); more vCPUs is better.
2. Among comparable candidates, prefer the one with the lower current
   `cpu_pct` (`mosaic_get_all_metrics`) — the least loaded.
3. Never place a compute step back on the dead node. Never move the traffic
   generator (counter 0). Do not place a step on a node that is itself offline.

## Acting
`mosaic_set_placement('audio_chain', [{"counter": C, "node_id": "<target>"}], reason="...")`
for each orphaned counter C, in a single call. `set_placement` rewires the
linear `forward_to` chain and redeploys the plan to the surviving nodes, so the
upstream step starts forwarding to the new location and the chain resumes.
Act in the SAME tick you detect the failure — do not defer.

## Cautions
- Migrate only the orphaned steps (those on the dead node). Do not reshuffle
  healthy steps.
- The jobs already lost during the outage do not come back; only new jobs
  benefit. Recovery = new jobs start completing again at healthy latency.
- If the ONLY sensible target is also offline, report `critical` and defer to
  the operator (nothing safe to do).

## Reporting / verdict
- `critical`: a node is DOWN and its `audio_chain` steps are still assigned to
  it (pipeline broken, no corrective migration issued yet).
- `warning`: you have just issued the healing migration; recovery in progress.
- `ok`: no `audio_chain` step is assigned to an offline node (healthy or healed).
Always justify with the observed node status and the target you chose (with its
capacity and load).
