---
name: mosaic-job-management
description: Knowledge for inspecting and reasoning about MOSAIC jobs, pipelines, and step execution. Use when the operator asks about job status, pipeline progress, step failures, or workload activity.
---

# MOSAIC Job Management

## Overview
MOSAIC executes distributed **pipelines** composed of **steps** across one or more nodes.
A **job** is a single execution instance of a pipeline.

## Data model

```
Pipeline (label)
  └── Job (job_id)
        └── Step (counter)
              ├── input_data
              ├── output_data
              └── execution_node
```

## Key tools

| Goal | Tool |
|---|---|
| List all active/recent jobs | `mosaic_get_all_jobs` |
| Get jobs for a specific pipeline | `mosaic_get_job_list` |
| Job execution timeline | `mosaic_get_job_timeline` |
| Step input/output inspection | `mosaic_get_step_data` |
| Node-level job list | `mosaic_list_node_jobs` |
| Node-level step detail | `mosaic_get_node_step` |

## Reasoning guidelines

1. **Active vs. completed**: `mosaic_get_all_jobs` returns both. Focus on `status: running` or `status: queued` for live issues.
2. **Stuck jobs**: a job is likely stuck if `created_at` is old and status is still `queued` — check node health.
3. **Step failures**: call `mosaic_get_node_step` for the failing step, then `mosaic_get_node_step_output` to read the error.
4. **Cross-node context**: a job may distribute steps across multiple nodes — check each node individually if needed.
5. **Traffic generators**: use `mosaic_get_traffic_generator_status` to see if synthetic load is active.
6. **Long queues — always paginate**: `mosaic_get_job_list` and `mosaic_get_job_results` return only the most recent `limit` jobs (default 20, cap 200), never the full backlog. Under a saturated pipeline (e.g. after a sustained heavy load) the queue can hold hundreds of jobs — requesting them all would overflow the model's context window. Rely on the default `limit`; only increase it if the operator explicitly needs more history, and check `pagination.truncated` before assuming you have the complete picture. Prefer `mosaic_get_job_list` (lighter, no output payload) over `mosaic_get_job_results` when you only need status counts or the most recent job_id — reach for `mosaic_get_job_results` only when the actual output/error content is needed.
7. **Summarise, don't enumerate**: when asked about a saturated pipeline, report aggregate counts by status (e.g. "42 queued, 3 running, 95 done out of 140 total") rather than listing every job_id — the totals are already in `pagination.total_count` and in the status field of each returned job.

## Typical diagnostic sequence
When the operator reports a job issue:
1. `mosaic_get_all_jobs` → find the job
2. `mosaic_get_job_timeline` → see step progression
3. If stuck: `mosaic_check_node_health` on the assigned node
4. If failed: `mosaic_get_node_step_output` for the error message
