"""Minimal REST client for the MOSAIC orchestrator managed by MASTRO."""
from __future__ import annotations

import httpx

from .adapter import base_url


def load_nodes_info(timeout: float = 5.0) -> dict:
    """Return MOSAIC's nodes_info (GET /api/nodes-info).

    Returns an empty topology when MOSAIC is unreachable, so callers can
    report "no nodes" instead of failing.
    """
    try:
        r = httpx.get(f"{base_url()}/api/nodes-info", timeout=timeout)
        r.raise_for_status()
        return r.json().get("nodes_info") or {"nodes": {}, "service_catalogs": {}}
    except (httpx.HTTPError, ValueError):
        return {"nodes": {}, "service_catalogs": {}}
