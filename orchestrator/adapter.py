"""MOSAIC implementation of the MASTRO infrastructure adapter contract."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parent


def base_url() -> str:
    return os.getenv("ORCHESTRATOR_URL", os.getenv("MOSAIC_URL", "http://127.0.0.1:9000")).rstrip("/")


def describe() -> dict:
    return {"id": "mosaic", "name": "MOSAIC", "url": base_url()}


def list_nodes() -> dict:
    from .discovery import load_nodes_info
    return {
        node_id: {"host": meta.get("host", "localhost"),
                  "runtime_port": meta.get("runtime_port") or meta.get("listen_port", 7000)}
        for node_id, meta in load_nodes_info().get("nodes", {}).items()
    }


def gateway_environment(*, node_ids: list[str] | None, port: int | None, mock_mode: bool) -> dict[str, str]:
    url = base_url()
    if port is not None:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        if ":" in host:
            host = f"[{host}]"
        url = urlunparse(parsed._replace(netloc=f"{host}:{port}"))
    env = {"ORCHESTRATOR_URL": url}
    if not mock_mode:
        nodes = list_nodes()
        selected = node_ids if node_ids is not None else list(nodes)
        unknown = set(selected) - nodes.keys()
        if unknown:
            raise ValueError(f"Unknown nodes: {', '.join(sorted(unknown))}")
        if not selected:
            raise ValueError("No runtime nodes available from MOSAIC.")
        env["MOSAIC_RUNTIME_NODES"] = ",".join(
            f"{nid}:{nodes[nid]['host']}:{nodes[nid]['runtime_port']}" for nid in selected
        )
    return env


def skills_dir() -> Path:
    return ROOT / "skills"


def default_agents() -> list[dict]:
    return [{
        "id": "agent-ops-001", "name": "Operations Agent",
        "description": "General-purpose operations agent for the MOSAIC use case.",
        "system_prompt": "You are a MASTRO operations agent for a MOSAIC edge datacenter. Help the operator understand the system state and suggest operational actions as requested.",
        "skills": ["mosaic-node-monitoring", "mosaic-job-management", "mosaic-topology"],
        "mcp_servers": [{"id": "mcp-gateway-001", "name": "MASTRO MCP Gateway", "url": "http://localhost:8001/mcp"}],
        "llm_override": None, "autonomous": None,
    }]


def cli_commands() -> list[tuple]:
    from .cli import COMMANDS
    return COMMANDS


def resolve_cli_url(args, config: dict) -> str:
    return (getattr(args, "orchestrator_url", None) or getattr(args, "mosaic_url", None)
            or os.getenv("ORCHESTRATOR_URL") or os.getenv("MOSAIC_URL")
            or config.get("orchestrator_url") or config.get("mosaic_url") or base_url()).rstrip("/")


def configure_cli(parser) -> None:
    parser.add_argument("--mosaic-url", help="MOSAIC URL (alias of --orchestrator-url)")


def configure_cli_config(subparsers, setter) -> None:
    parser = subparsers.add_parser("set-mosaic-url", help="Alias of set-orchestrator-url for MOSAIC")
    parser.add_argument("backend_url")
    parser.set_defaults(func=setter("orchestrator_url"))
