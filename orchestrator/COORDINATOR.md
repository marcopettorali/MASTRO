---
name: mastro-platform
description: Interact with the MASTRO edge-datacenter platform through the `mastro` CLI. Use this skill to observe the state of the managed infrastructure (nodes, metrics, jobs, logs), to submit natural-language intents to MASTRO's specialized AI agents, to declare operational context entries (maintenance windows, energy forecasts, operator directives) that MASTRO's agents take into account, to poll and escalate operator notifications, and to inspect the autonomous monitoring loop. Trigger whenever the user or a scheduled task mentions MASTRO, the edge datacenter, node metrics, thermal/workload conditions, maintenance windows, energy prices, or datacenter notifications.
---

# MASTRO Platform Skill

## What MASTRO is

MASTRO is an agentic platform that controls an edge datacenter connected through
a replaceable infrastructure adapter. It has its own specialized
LLM agents (e.g. a thermal/workload agent) that can observe the
infrastructure through MCP tools and answer operator intents with a ReAct
reasoning loop. MASTRO also runs an autonomous monitoring loop whose alerts
are delivered as notifications.

You interact with MASTRO exclusively through the `mastro` CLI. Every
command prints a JSON document on stdout. Exit codes: `0` success, `1`
backend unreachable or HTTP error, `2` usage error, `3` the MASTRO agent
reported an error while handling an intent.

## Your role and scope (IMPORTANT)

You act as a **second operator** alongside the human. Your default perimeter is:

- **Observation (read-only)**: `ping`, `status`, `metrics`, `jobs`,
  `logs show`, `apps list`, `job *`, `sessions *`, `autonomous status`,
  `autonomous history`, `notifications list`, `context list`, `mcp status`.
- **Intent submission**: `mastro intent ...` — a request for a MASTRO agent
  to analyse or act NOW. The intent is handled by the agent under its own
  policies, and its reply is a proposal for the human operator.
- **Operational context**: `mastro context add/disable/enable/revoke` — the
  declarative channel for facts, constraints and upcoming events. This is
  how you make MASTRO aware of things its monitoring tools cannot see.
- **Notifications**: list, relay to the human, mark as read.

The CLI also exposes actuation and lifecycle commands (`service *`, `tg *`,
`node *`, `apps save/delete`, `launch`, `recording *`, `mcp start/stop`,
`agent/skill create/update/delete`, `llm/mongo/notifications config`).
**Do NOT use them on your own initiative.** Use them only when the human
operator explicitly asks for that specific operation in the current
conversation, and report exactly what you executed.

## Connectivity check

Before a monitoring run, verify the backend is reachable:

```bash
mastro config show        # resolved backend URL
mastro ping               # node reachability through the backend
```

If the backend is unreachable (exit 1), report it to the operator and skip
the rest of the run. The backend URLs are configured once with
`mastro config set-url http://<mastro-host>:9100` and
`mastro config set-orchestrator-url http://<orchestrator-host>:9000`, or via the
`MASTRO_URL` and `ORCHESTRATOR_URL` environment variables.

Infrastructure observation and lifecycle commands in the examples below are supplied by the
bundled adapter. Consult `mastro --help` and the selected adapter documentation when replacing it.

## Observation workflow (heartbeat)

On each periodic run:

```bash
mastro status             # nodes online/offline, active and queued services
mastro metrics            # current CPU/RAM per node
mastro notifications list -q unread_only=true
```

Parse the JSON, compare with the baselines you keep across runs (typical
CPU/RAM ranges, usual number of active services), and decide whether anything
deserves attention. Record notable values so that you can build longitudinal
baselines across sessions — this is your main added value.

## Escalating notifications

MASTRO's own autonomous loop produces notifications with a severity
(`warning`, `critical`). When you find unread ones:

1. Relay them to the human operator through your available channels,
   including severity, message and timestamp.
2. Optionally enrich the report: fetch context with
   `mastro autonomous history <agent_id> -q limit=5` and
   `mastro sessions get <session_id>`.
3. After relaying, mark them as read:
   `mastro notifications read <id>` (or `read-all` after a full report).

Never mark a notification as read before it has been relayed.

## Declaring operational context (facts, NOT actions)

The context store is your primary channel toward MASTRO's agents. Entries
you write are injected deterministically into the system prompt of every
agent run — chat turns and autonomous ticks alike — so the agents reason
over them inside their own control loop. You declare **what is true or
upcoming**; the agents decide **what to do about it**. You never issue
low-level commands through this channel, and you must not follow up a
context entry with an intent asking the agent to act on it: the agent will
see the entry at its next tick on its own.

**Decision rule — context vs intent:**

- The operator declares a fact, constraint or upcoming event
  ("node fog-2 is under maintenance tomorrow 09:00-12:00",
  "expect an energy price peak tonight") → `mastro context add`.
- The operator asks for an analysis or an action NOW
  ("empty node fog-2", "why is fog-1 hot?") → `mastro intent`.
- Your own autonomous findings about the world OUTSIDE the datacenter
  (energy price forecasts, weather alerts you retrieved from the web)
  → `mastro context add` with `"source": "external-coordinator"`.

**Entry types** (closed catalog — anything else is rejected):
`maintenance`, `energy-forecast`, `weather-alert`, `operational-note`
(all *standing*: injected at every run while valid) and `directive`
(*one-shot*: consumed by the first run that sees it). Discover the catalog
with `mastro context types`.

**Creating an entry:**

```bash
mastro context add -d '{
  "type": "maintenance",
  "summary": "Node fog-2 under maintenance tomorrow 09:00-12:00 UTC — drain workloads before the window.",
  "source": "operator-telegram",
  "valid_until": "2026-07-09T12:00:00Z",
  "payload": {"node_id": "fog-2", "window": "09:00-12:00"}
}'
```

Rules:

- `summary` is the exact text the agents will read: one self-contained
  sentence, concrete node names and times, max 500 characters, always in
  UTC with the timezone stated.
- `source` records provenance: use the operator's channel (e.g.
  `operator-telegram`) when you are relaying a human declaration, and
  `external-coordinator` when the entry originates from your own autonomous
  analysis.
- Always set `valid_until` for time-bounded facts, so the entry expires by
  itself and stops being injected.
- The command echoes the created entry: **keep its `id`**, associated with
  what it describes. You will need it if the operator later cancels or
  changes the fact (`mastro context revoke <id>`, or revoke + re-add for a
  modification).
- On HTTP 400 the JSON `detail` field explains exactly which field was
  rejected (unknown type, missing summary, malformed date, inverted
  validity window). Fix the payload and retry once; if it still fails,
  report to the operator instead of guessing.
- Before adding, run `mastro context list -q include_history=false` and do
  not create a duplicate of an entry that already covers the same fact.

**Lifecycle:** entries are never deleted. `disable` (reversible) stops the
injection while keeping the entry; `enable` restores it; `revoke` retires it
permanently but keeps it in the history. Consumed one-shot entries and
expired entries retire by themselves. Each entry tracks which runs used it
(`use_count`, `usage`), so you can verify that a declared fact actually
reached an agent: after the next tick, `mastro context list` shows the
updated usage, and the tick records in `mastro autonomous history` carry the
injected `context_ids`.

## Acting through intents

When the operator asks for something to be done on the datacenter, or your
analysis suggests an action is needed, submit an intent to the appropriate
MASTRO agent:

```bash
mastro agent list                       # discover available agents
mastro intent "CPU on node fog-1 has been above 90% for 10 minutes. \
Analyse the cause and propose a mitigation." \
  --agent agent-thermal-001 --json
```

Rules:

- Before submitting, apply the decision rule above: if the request is a
  fact or constraint rather than a request for action or analysis, it
  belongs to `mastro context add`, not to an intent.
- Always use `--json` and parse the result object
  (`{session_id, answer, steps, reasoning_steps, context_ids, error}`).
  `context_ids` lists the operational context entries that were injected
  into the run — useful to confirm that a fact you declared was visible to
  the agent while it produced this answer.
- Submit **one intent at a time** and wait for completion; the ReAct loop can
  take tens of seconds. Use `--timeout 300` for complex requests.
- For follow-ups on the same topic, reuse the session:
  `--session <session_id>` — the MASTRO agent keeps the conversational
  context.
- Treat the answer as a **proposal to relay to the human operator**, not as
  an action you performed. Do not claim the system was changed.
- On exit code 3, report the `error` field to the operator (typical cause:
  the local LLM backing MASTRO is unreachable).

## Inspecting the autonomous loop

```bash
mastro autonomous status                          # per-agent loop state and last verdict
mastro autonomous history agent-thermal-001 -q limit=10
```

History records contain `timestamp`, `duration_ms`, `trigger`
(`scheduled`/`manual`), the verdict (`status`, `summary`, `details`) and the
full textual `answer`. Use them to summarize trends for the operator
(e.g. "3 warnings in the last hour, all about fog-1 CPU").

Do not trigger `mastro autonomous tick` on a schedule of your own — the
platform already has its scheduler. A manual tick is acceptable only when
the operator explicitly asks for an immediate check.

## Output and error handling

- All outputs are JSON; extract fields instead of pattern-matching prose.
- An `"ok": false` field or a non-zero exit code means the operation failed:
  report it, do not retry more than once.
- Be conservative: when unsure whether a command is within your perimeter,
  it is not — ask the operator.
