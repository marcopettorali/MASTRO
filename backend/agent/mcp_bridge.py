"""MCP Bridge — calls tools on the running MASTRO MCP Gateway.

The gateway must already be running (started from the MCP Gateway tab).
Uses the fastmcp Client which handles the streamable-HTTP MCP protocol.

Provides:
  list_tools(url)          — returns list of MCP tool definitions
  call_tool(url, name, args) — executes a tool and returns string result
  to_openai_tools(tools)   — converts MCP tool list to OpenAI tools format
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("mastro.mcp_bridge")


async def list_tools(mcp_url: str) -> list[dict]:
    """Return all tools exposed by the MCP server."""
    try:
        from fastmcp import Client  # type: ignore
        async with Client(mcp_url) as client:
            tools = await client.list_tools()
            result = []
            for t in tools:
                # MCP SDK v2 renamed Tool.inputSchema to Tool.input_schema:
                # prefer the new name, fall back to the old one.
                schema = getattr(t, "input_schema", None)
                if schema is None:
                    schema = getattr(t, "inputSchema", None) or {}
                result.append({
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": schema,
                })
            return result
    except ImportError:
        logger.error("fastmcp not installed")
        return []
    except Exception as exc:
        logger.warning("list_tools failed (%s): %s", mcp_url, exc)
        return []


async def call_tool(mcp_url: str, name: str, arguments: dict) -> str:
    """Call a named tool and return its result as a string.

    fastmcp.Client.call_tool() returns a CallToolResult dataclass:
        CallToolResult.content  -> list[ContentBlock]
        CallToolResult.structured_content -> dict | None
        CallToolResult.is_error -> bool

    ContentBlock is a Union of TextContent, ImageContent, etc.
    TextContent has a .text attribute.
    """
    try:
        from fastmcp import Client  # type: ignore
        async with Client(mcp_url) as client:
            result = await client.call_tool(name, arguments)

            # result is CallToolResult — iterate over result.content
            content_items = getattr(result, "content", None)

            # Fallback: some older fastmcp versions return list directly
            if content_items is None and hasattr(result, "__iter__"):
                content_items = list(result)

            if not content_items:
                # Try structured_content as fallback
                structured = getattr(result, "structured_content", None)
                if structured:
                    return json.dumps(structured, ensure_ascii=False)
                return "(no output)"

            parts = []
            for item in content_items:
                if hasattr(item, "text"):
                    parts.append(item.text)
                elif hasattr(item, "data"):
                    parts.append(str(item.data))
                else:
                    parts.append(str(item))
            return "\n".join(parts) if parts else "(no output)"

    except ImportError:
        return "Error: fastmcp not installed"
    except Exception as exc:
        logger.warning("call_tool '%s' failed: %s", name, exc)
        return f"Tool error: {exc}"


def to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert MCP tool list to OpenAI function-calling format."""
    openai_tools = []
    for t in tools:
        schema = t.get("inputSchema") or {}
        # Ensure schema is a valid JSON Schema object
        if not isinstance(schema, dict):
            schema = {}
        if "type" not in schema:
            schema = {"type": "object", "properties": {}, **schema}
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": schema,
            },
        })
    return openai_tools
