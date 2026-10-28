"""Platform gateway management tools, independent of the infrastructure adapter."""
import os
import httpx


def register(mcp, *, mock_mode=False):
    is_mock = mock_mode
    async def request(method, path, **kwargs):
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(method, os.getenv("MASTRO_URL", "http://localhost:9100").rstrip("/") + path, **kwargs)
            response.raise_for_status()
            return response.json()

    @mcp.tool()
    async def mastro_mcp_status() -> dict:
        """Status of the gateway process managed by MASTRO."""
        if mock_mode:
            return {"ok": True, "running": True, "mock_mode": True}
        return await request("GET", "/api/mcp/status")

    @mcp.tool()
    async def mastro_mcp_logs(lines: int = 80) -> dict:
        """Recent logs from the gateway managed by MASTRO."""
        if mock_mode:
            return {"ok": True, "lines": ["[mock] MCP server running"]}
        return await request("GET", "/api/mcp/logs", params={"lines": lines})

    @mcp.tool()
    async def mastro_mcp_nodes() -> dict:
        """Discover normalized nodes from the active infrastructure adapter."""
        if mock_mode:
            return {"ok": True, "nodes": {}}
        return await request("GET", "/api/mcp/nodes")

    @mcp.tool()
    async def mastro_mcp_start(mock_mode: bool = False, dry_run: bool = False,
                              transport: str = "http", port: int = 8001,
                              node_ids: list[str] | None = None,
                              orchestrator_port: int | None = None) -> dict:
        """Start the MASTRO-managed gateway (the current process must be stopped first)."""
        if is_mock:
            return {"ok": True, "pid": 99999, "config": {"transport": transport, "port": port}}
        return await request("POST", "/api/mcp/start", json={
            "mock_mode": mock_mode, "dry_run": dry_run, "transport": transport,
            "port": port, "node_ids": node_ids, "orchestrator_port": orchestrator_port,
        })

    @mcp.tool()
    async def mastro_mcp_stop() -> dict:
        """Stop the MASTRO-managed gateway process."""
        if is_mock:
            return {"ok": True, "message": "Gateway stopped (mock)"}
        return await request("POST", "/api/mcp/stop")
