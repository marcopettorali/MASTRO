from __future__ import annotations

from pydantic import BaseModel


class MCPStartRequest(BaseModel):
    mock_mode:       bool       = False
    dry_run:         bool       = False
    transport:       str        = "http"      # "http" | "stdio"
    port:            int        = 8001
    node_ids:        list[str] | None = None  # None = all nodes
    orchestrator_port: int | None = None  # Optional adapter endpoint port override
