# MASTRO CLI

Install from the repository root:

```bash
./scripts/install_cli.sh
# Or, in a virtual environment:
pip install . ./cli
```

The CLI loads infrastructure commands from `orchestrator/`; platform commands remain available
with any adapter. Deployments on other machines need both the CLI and the chosen adapter package.

```bash
mastro config set-url http://mastro-host:9100
mastro config set-orchestrator-url http://orchestrator-host:9000
mastro config show
mastro agent list
mastro intent "Summarize the infrastructure state" --agent <agent_id> --trace
mastro context list
mastro notifications list
```

Platform groups: `agent`, `skill`, `intent`, `sessions`, `autonomous`, `context`, `notifications`,
`mcp`, `llm`, `mongo`. Infrastructure groups are supplied by the adapter; run `mastro --help`
to inspect the active command set. See the bundled adapter's [command reference](../orchestrator/CLI.md).

MASTRO URL precedence: `--url`, `MASTRO_URL`, `~/.mastro/config.json` key `url`, then
`http://127.0.0.1:9100`. The adapter resolves the infrastructure URL, using the generic
`--orchestrator-url`, `ORCHESTRATOR_URL`, and `orchestrator_url` config key.

`-q K=V` adds query parameters, `-d JSON|@file` provides a JSON body, and `--form K=V` /
`--file FIELD=PATH` provide multipart data. `--timeout SECONDS` changes the request timeout.
For intents, `--session ID` continues a conversation and `--json` emits one JSON result.
Exit codes: `0` success, `1` request failure, `2` usage error, `3` agent failure.

[SKILL.md](SKILL.md) describes the CLI for an external coordinator; infrastructure-specific
operating procedures belong to the adapter's skills.
