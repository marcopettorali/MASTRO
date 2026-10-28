# Infrastructure adapter contract

`orchestrator/` is the single replaceable integration package. The core imports its public
functions; it does not import a concrete orchestrator client, endpoint map or tool name.
Implement these functions in `orchestrator/__init__.py` (internal layout is up to the adapter):

| Function | Contract |
|----------|----------|
| `describe()` | JSON-serializable `{id, name, url}` metadata |
| `base_url()` | Configured infrastructure URL as a string |
| `list_nodes()` | `{node_id: {host, runtime_port}}` for the gateway node selector; `{}` if unavailable |
| `gateway_environment(*, node_ids, port, mock_mode)` | String environment overrides for the gateway subprocess; validate node selection and raise `ValueError` with an actionable message on failure |
| `gateway_instructions()` | MCP server instructions describing this infrastructure |
| `register_tools(mcp)` | Register infrastructure tools on a `fastmcp.FastMCP` instance |
| `skills_dir()` | A `pathlib.Path` containing `<skill-name>/SKILL.md` directories, writable for the skill editor |
| `default_agents()` | List of default agent profiles, including relevant skill names and MCP endpoints |
| `cli_commands()` | List of `(group, subcommand_or_None, method, path, help)` tuples for the infrastructure CLI |
| `resolve_cli_url(args, config)` | Resolve the infrastructure CLI URL; honor generic flag/env/config settings |
| `configure_cli(parser)` | Register optional adapter-specific global CLI flags; may do nothing |
| `configure_cli_config(subparsers, setter)` | Register optional config subcommands; `setter(key)` supplies a URL-saving handler; may do nothing |

The install hook `python -m orchestrator init-config <directory>` initializes `agents.json` from
`default_agents()` only when it does not already exist. The replacement package must provide
this hook too; it can reuse the supplied generic `__main__.py`.

The platform controls `MOCK_MODE`, `DRY_RUN` and the gateway HTTP/stdio transport. The adapter
implements the mock and dry-run semantics of its infrastructure tools. It may use
`MASTRO_MCP_TOOLS` to select modules. MASTRO gateway lifecycle tools (`mastro_mcp_*`) are
registered separately by the transport; adapters must not duplicate them. Generic CLI groups
(`agent`, `skill`, `mcp`, `intent`, `sessions`, `autonomous`, `context`, `notifications`, `llm`,
`mongo`, `config`) are reserved by the platform.

## Replacement procedure

1. Stop the gateway and MASTRO.
2. Replace the entire `orchestrator/` directory, including its domain skills and examples.
3. Run `./scripts/install.sh`. The root package definition installs `orchestrator` and its
   subpackages; include additional dependencies in the adapter's `requirements.txt`, which the
   installer reads when present. Re-run `./scripts/install_cli.sh` if the CLI is installed.
4. Set `ORCHESTRATOR_URL` and any adapter-specific settings. Update preserved agent profiles to
   use the replacement's skills, tool names and endpoints.
5. Restart MASTRO and test discovery and tools. No platform source edits are required.

For a source checkout the backend adds the repository root to the gateway subprocess's
`PYTHONPATH`. For standalone installation, install both packages from the repository root:

```bash
pip install . ./mcp_gateway ./cli
```

After replacing an adapter in an already running interpreter, restart it: Python caches imports.
The contract does not require another orchestrator to reproduce MOSAIC's REST routes, runtime
configuration format or tool names. Those belong exclusively to the adapter implementation.
