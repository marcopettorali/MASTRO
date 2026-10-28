"""Generic MCP transport hosting the tools supplied by orchestrator/."""
from __future__ import annotations

import argparse
import logging
import os
import sys

from fastmcp import FastMCP
import orchestrator as adapter
from .tools import control

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s", stream=sys.stderr)
logger = logging.getLogger("mastro.mcp_gateway")

mcp = FastMCP(name="mastro-mcp-gateway", instructions=adapter.gateway_instructions())
adapter.register_tools(mcp)
control.register(mcp, mock_mode=os.getenv("MOCK_MODE", "false").lower() == "true")


def main() -> None:
    parser = argparse.ArgumentParser(description="MASTRO MCP Gateway")
    parser.add_argument("--http", action="store_true", help="Use Streamable HTTP instead of stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    logger.info("MASTRO MCP Gateway; adapter=%s", adapter.describe())
    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
