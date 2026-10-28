"""Replaceable infrastructure adapter; see docs/adapter-contract.md."""
from .adapter import (
    base_url, describe, list_nodes, gateway_environment, skills_dir,
    default_agents, cli_commands, resolve_cli_url, configure_cli, configure_cli_config,
)


def register_tools(mcp):
    from .gateway import register_tools as register
    register(mcp)


def gateway_instructions():
    from .gateway import INSTRUCTIONS
    return INSTRUCTIONS
