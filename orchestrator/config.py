"""
MASTRO MCP Gateway configuration.
Every parameter can be overridden through environment variables.
"""

import os
from dataclasses import dataclass, field
from .adapter import base_url


@dataclass
class Config:
    # ── Orchestrator ─────────────────────────────────────────────────────────
    orchestrator_host: str = os.getenv("MOSAIC_HOST", "localhost")
    orchestrator_port: int = int(os.getenv("MOSAIC_GUI_PORT", "9000"))
    orchestrator_base_url: str = ""           # computed in __post_init__

    # ── Runtime nodes (host:port per node, comma-separated or from nodes_info) ─
    # Example: "fog1:7000,fog2:7001,server:7002"
    runtime_nodes_str: str = os.getenv("MOSAIC_RUNTIME_NODES", "")
    runtime_nodes: dict[str, str] = field(default_factory=dict)  # {node_id: "host:port"}

    # ── HTTP client ──────────────────────────────────────────────────────────
    timeout_s: float = float(os.getenv("MOSAIC_TIMEOUT", "10"))
    retries: int = int(os.getenv("MOSAIC_RETRIES", "2"))

    # ── Mock mode ────────────────────────────────────────────────────────────
    mock_mode: bool = os.getenv("MOCK_MODE", "false").lower() == "true"

    # ── Dry-run mode (log write actions without executing them) ─────────────
    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"

    # ── Rate limiting (write tools) ──────────────────────────────────────────
    write_min_interval_s: float = float(os.getenv("MOSAIC_WRITE_INTERVAL", "5"))

    def __post_init__(self):
        self.orchestrator_base_url = (
            base_url() if os.getenv("ORCHESTRATOR_URL") or os.getenv("MOSAIC_URL")
            else f"http://{self.orchestrator_host}:{self.orchestrator_port}"
        )
        # parse runtime nodes from the string "id:host:port,id:host:port"
        if self.runtime_nodes_str:
            for entry in self.runtime_nodes_str.split(","):
                parts = entry.strip().split(":")
                if len(parts) == 3:
                    node_id, host, port = parts
                    self.runtime_nodes[node_id.strip()] = f"http://{host.strip()}:{port.strip()}"


# Global singleton
cfg = Config()
