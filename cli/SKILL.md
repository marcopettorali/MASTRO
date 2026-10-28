---
name: mastro-platform
description: Use the mastro CLI to submit intents, inspect agents and sessions, declare operational context, review notifications and manage autonomous monitoring.
---

# MASTRO platform

MASTRO connects LLM agents to managed infrastructure through a replaceable adapter. Use the
`mastro` CLI to interact with its platform API. Infrastructure commands and operating procedures
are supplied by the selected adapter; inspect `mastro --help` and the adapter documentation.

## Default operating scope

Observe agents, sessions, context and notifications; submit natural-language intents when asked;
record operational facts through the context API. Use configuration, deployment and lifecycle
commands only when the operator requests them.

```bash
mastro config show
mastro agent list
mastro mcp status
mastro intent "Summarize the infrastructure state" --agent <agent_id> --trace
mastro context list
mastro notifications list
mastro autonomous status
mastro sessions list
```

Set the platform URL with `mastro config set-url http://mastro-host:9100`. Set the infrastructure
URL with `mastro config set-orchestrator-url http://orchestrator-host:9000`; adapters may supply
other configuration options. `MASTRO_URL` and `ORCHESTRATOR_URL` override saved URLs.

Commands print JSON. Use `-q K=V` for query parameters and `-d JSON|@file` for JSON bodies. Intent
commands support `--session ID`, `--trace` and `--json`. Exit codes: `0` success, `1` request
failure, `2` invalid usage, `3` agent error. If a backend is unreachable, report the error and
avoid dependent actions.

Infrastructure-specific observation and intervention workflows belong to the selected adapter,
so changing adapters does not preserve assumptions about tool names or resource models.
