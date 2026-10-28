---
name: mosaic-rebalancing
description: Decision procedure for rebalancing workload across MOSAIC nodes by migrating pipeline steps (service reallocation). Use when a node is saturated or overheating and the operator asks to rebalance, migrate a service, or when autonomous policy authorises corrective placement actions.
---

# MOSAIC Workload Rebalancing (service reallocation)

## Overview
When a node is saturated (sustained high CPU, growing job queue, temperature
above threshold) and another node has spare capacity, the corrective action
is to **migrate the compute-heavy pipeline step** to the less loaded node.
In MOSAIC this is a placement change: each pipeline step has a `node_id`,
and `mosaic_set_placement` rewrites it and redeploys the plan files.

## Decision procedure

1. **Confirm the imbalance** — `mosaic_get_all_metrics`: identify the
   saturated node (cpu_pct, temp_c) and the candidate target (low cpu_pct,
   low temp_c, status online via `mosaic_get_system_status`).
2. **Confirm the cause** — `mosaic_get_all_jobs` / `mosaic_get_job_list`:
   the saturated node must actually be running/queueing the heavy steps.
   Do not migrate because of a load spike not tied to a pipeline.
3. **Locate the step to move** — `mosaic_get_applications` and
   `mosaic_get_application_steps(app_name)`: find the step `counter`
   whose `service_ref` is the compute service (e.g. `cpu_stress`) and
   whose `node_id` is the saturated node. Do **not** move the traffic
   generator step (counter 0): the load source stays where it is, only
   the compute step migrates.
4. **Act** — `mosaic_set_placement(app_name, [{"counter": C, "node_id":
   "<target>"}], reason="...")` with an explicit, data-grounded reason.
5. **Verify** — after 1–2 minutes re-read metrics and jobs: CPU and
   temperature on the origin node must decrease (temperature with thermal
   inertia), new jobs must execute on the target node, the queue on the
   origin must drain.

## Cautions

- One migration at a time; verify before further action (avoid ping-pong).
- If **all** nodes are loaded, migration does not help: report `critical`
  and defer to the operator instead of shuffling load.
- The queue already accumulated on the origin node is drained locally;
  only new jobs benefit from the new placement. Say so in your answer.
- In dry-run mode the tool responds with `dry_run: true` and nothing
  changes: state clearly that no action was applied.

## Reporting

When you perform (or simulate) a reallocation, always report: origin node
and its readings, target node and its readings, the step moved
(app, counter, service), and the verification you will perform next.
