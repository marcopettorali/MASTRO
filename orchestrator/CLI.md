# mastro - MASTRO platform CLI

Command-line interface for MASTRO and the MOSAIC orchestrator it manages. It covers the REST
surface of both backends:

- **MASTRO**: MCP Gateway control, agents and skills, LLM/MongoDB/notification configuration,
  natural-language intent submission (with SSE streaming), sessions, the autonomous loop,
  notifications and operational context;
- **MOSAIC**: monitoring, applications and placement, jobs, recordings, services, traffic
  generators and node lifecycle.

Each command is sent to the backend it belongs to.

The CLI is a single Python file (`mastro_cli.py`) with a single dependency (`httpx`). It is meant
to be installable on machines other than the one hosting the backend, for example the instance
that runs an external coordinator.

The command is called `mastro`; `mosaic` is still available as an alias.

---

## 1. Requirements and installation

Requirements: Python >= 3.10.

**Guided installation (recommended):** the script creates a dedicated virtual environment,
installs the command, asks for the backend port and makes `mastro` callable from any shell.

```bash
./scripts/install_cli.sh            # interactive
./scripts/install_cli.sh --port 9100
```

**Installation as a package:**

```bash
pip install . ./cli
mastro --help
```

The `mastro` entry point is added to the PATH. On Ubuntu 24.04 with the system
Python you may need `pip install . --break-system-packages`, or a dedicated virtualenv.

**Minimal installation on a remote instance:** copying the CLI and adapter packages are required:

```bash
pip install . ./cli
```

## 2. Starting the backends

The CLI talks to the MASTRO backend (default port 9100) and to the MOSAIC backend (default port
9000). Start MOSAIC as described in its README, then MASTRO:

```bash
cd <MASTRO repository root>
./scripts/start.sh
```

The MASTRO backend listens on `0.0.0.0`, so it is also reachable from remote instances. The Agent
Scheduler and the Notification Service start automatically together with the backend.

## 3. CLI configuration

The two backend URLs are resolved in this order:

| | MASTRO | MOSAIC |
|---|---|---|
| 1. flag on the individual command | `--url` | `--mosaic-url` |
| 2. environment variable | `MASTRO_URL` | `MOSAIC_URL` |
| 3. `~/.mastro/config.json` | `url` | `mosaic_url` |
| 4. default | `http://127.0.0.1:9100` | `http://127.0.0.1:9000` |

For a remote instance, the persistent configuration is the most convenient:

```bash
mastro config set-url http://mastro-host:9100
mastro config set-mosaic-url http://mosaic-host:9000
mastro config show
```

## 4. Conventions

- **Output**: every command prints the backend's JSON response to stdout, pretty-printed and
  directly parsable (`jq`, `python -c`).
- **`-q KEY=VALUE`** (repeatable): adds query-string parameters.
  Example: `mastro logs show -q limit=100`.
- **`-d JSON | -d @file.json`**: request body for write commands.
  Example: `mastro agent update <id> -d @agent.json`.
- **`--form K=V` / `--file FIELD=PATH`** (repeatable): multipart fields and files for upload
  commands.
- **`--timeout SECONDS`**: request timeout (default 30 s; use higher values for long deploy
  operations, e.g. `--timeout 300`).

**Exit codes**: `0` success, `1` HTTP error or backend unreachable, `2` usage error, `3` agent
error during an intent. Designed for scripting and for agent branching.

## 5. Command reference

### System and monitoring
| Command | Description |
|---|---|
| `mastro ping` | Ping the MOSAIC nodes |
| `mastro status` | Aggregated status (nodes, services, queues) |
| `mastro metrics` | Current CPU/RAM metrics of all nodes |
| `mastro jobs` | Aggregated job status |
| `mastro logs show [-q limit=N]` | Recent node logs |
| `mastro logs clear` | Clear the collected logs |
| `mastro launch` | Launch the configured job |
| `mastro nodes show` / `nodes save -d` | Node topology |

### Applications and placement
| Command | Description |
|---|---|
| `mastro apps list` | Pipelines and current placements |
| `mastro apps save -d` | Save the modified placements |
| `mastro apps delete -d` | Delete an application |
| `mastro apps steps` | Pipeline steps |
| `mastro apps deploy-plans` | Distribute the plan files to all nodes |
| `mastro apps deploy-plans-for -d` | Plan files for a single application |

### Inputs and jobs
| Command | Description |
|---|---|
| `mastro inputs show` / `save -d` / `upload --file file=PATH` | Input management |
| `mastro job list` / `timeline` / `results` / `step-data` / `tg-deployments` | Job details (filters with `-q`) |

### Recordings
`mastro recording metrics-start -d` / `metrics-stop` / `metrics-status` / `metrics-list`, and
the equivalent `perf-*` commands for performance recordings.

### Services, traffic generators, nodes
| Group | Subcommands |
|---|---|
| `mastro service` | `list`, `configure -d`, `delete -d`, `deploy -d`, `deploy-all`, `assets -d`, `build-images -d`, `sync-catalogs`, `sync`, `upload-catalog --form/--file`, `upload-files --form/--file` |
| `mastro tg` | `list`, `list-local`, `status`, `start -d`, `stop -d`, `deploy -d`, `delete -d`, `upload --form/--file` |
| `mastro node` | `sync-clock -d`, `restart-runtime -d`, `check-sync -d`, `full-sync -d`, `deploy-configs -d`, `deploy-runtime -d`, `install -d`, `uninstall -d` |

### MCP Gateway, agents, skills, configuration
| Group | Subcommands |
|---|---|
| `mastro mcp` | `status`, `logs`, `nodes`, `start`, `stop`, `test -d '{"url": ...}'` |
| `mastro agent` | `list`, `get ID`, `create -d`, `update ID -d`, `delete ID` |
| `mastro skill` | `list`, `get NAME`, `create -d`, `update NAME -d`, `delete NAME` |
| `mastro llm` | `get`, `set -d` |
| `mastro mongo` | `get`, `set -d`, `test -d` |

### Intents (natural language)
```bash
mastro intent "What is the thermal state of the nodes?" --agent agent-thermal-001
```
Options: `--session ID` to continue an existing session, `--trace` to print the ReAct trace
(thought/action/observation) to stderr, `--json` to get a single JSON object
`{session_id, answer, steps, reasoning_steps, context_ids, error}` instead of the text stream.
The session identifier is always reported (`X-Session-Id` header).

### Sessions, autonomous loop, context, notifications
| Group | Subcommands |
|---|---|
| `mastro sessions` | `list [-q agent_id= -q limit=]`, `get ID`, `delete ID` |
| `mastro autonomous` | `status`, `tick AGENT_ID`, `history AGENT_ID [-q limit=N]` |
| `mastro context` | `list [-q include_history=false]`, `types`, `add -d`, `enable ID`, `disable ID`, `revoke ID` |
| `mastro notifications` | `list [-q unread_only=true]`, `read ID`, `read-all`, `config`, `config-set -d`, `test -d` |

## 6. Examples

**Quick supervision from the terminal:**
```bash
mastro status
mastro metrics | jq '.metrics'
mastro notifications list -q unread_only=true
```

**Enable an agent's autonomous loop:**
```bash
mastro agent update agent-thermal-001 -d '{
  "autonomous": {"enabled": true, "interval_seconds": 120,
                  "task_prompt": "Analyze the thermal and load state of the nodes.",
                  "notify_on": ["warning", "critical"]}
}'
mastro autonomous status
```

**Repeated ticks and history collection:**
```bash
for i in $(seq 1 10); do
  mastro autonomous tick agent-thermal-001 > /dev/null
  sleep 30
done
mastro autonomous history agent-thermal-001 -q limit=100 > history.json
```

**Declare a maintenance window (operational context):**
```bash
mastro context add -d '{
  "type": "maintenance",
  "summary": "Node fog-2 under maintenance tomorrow 09:00-12:00 UTC.",
  "source": "operator",
  "valid_until": "2026-07-09T12:00:00Z"
}'
```

**Conversation with a persistent session:**
```bash
SID=$(mastro intent "Summarize the system status" \
        --agent agent-thermal-001 --json | jq -r .session_id)
mastro intent "How does it compare to an hour ago?" --agent agent-thermal-001 --session $SID
```

## 7. Use by an external coordinator

The `SKILL.md` document in this folder describes, for an external agent that uses the CLI, the
recommended operating scope (observation, intents, operational context, notifications) and usage
examples. Copy it into the external agent's skills directory.

## 8. Troubleshooting

- `cannot reach MASTRO backend` / `cannot reach MOSAIC backend`: check that the backend is
  running, that the configured URL is correct (`mastro config show`) and that the port (9100 for
  MASTRO, 9000 for MOSAIC) is reachable from the instance (firewall).
- `exit code 3` on an intent: the agent hit an error (typically the LLM is unreachable); the
  message is in the `error` field of the `--json` output or on stderr.
- Uploads: the multipart field name must match the one expected by the endpoint (e.g.
  `--file file=data.json` for `inputs upload`; `--form service_name=X --form mode=docker --file ...`
  for `service upload-catalog`).
- Timeouts on deploy/sync operations: increase with `--timeout 300`.
