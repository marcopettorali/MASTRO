"""
Base HTTP client with retries, timeouts and uniform error handling.
All specific clients build on it.
"""

import logging
from typing import Any

import httpx

from ..config import cfg

logger = logging.getLogger("mastro.mcp_gateway.http")


class MosaicHTTPError(Exception):
    def __init__(self, status: int, url: str, body: str):
        self.status = status
        self.url = url
        self.body = body
        super().__init__(f"HTTP {status} from {url}: {body[:200]}")


async def _get(url: str, params: dict | None = None) -> Any:
    """GET with retries and timeout. Returns the parsed JSON."""
    last_err: Exception | None = None
    for attempt in range(cfg.retries + 1):
        try:
            async with httpx.AsyncClient(timeout=cfg.timeout_s) as client:
                r = await client.get(url, params=params)
                if r.status_code >= 400:
                    raise MosaicHTTPError(r.status_code, url, r.text)
                return r.json()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_err = e
            if attempt < cfg.retries:
                logger.warning("GET %s attempt %d/%d failed: %s", url, attempt + 1, cfg.retries + 1, e)
    raise last_err  # type: ignore


async def _post(url: str, payload: dict | None = None, params: dict | None = None) -> Any:
    """POST with retries and timeout."""
    last_err: Exception | None = None
    for attempt in range(cfg.retries + 1):
        try:
            async with httpx.AsyncClient(timeout=cfg.timeout_s) as client:
                r = await client.post(url, json=payload or {}, params=params)
                if r.status_code >= 400:
                    raise MosaicHTTPError(r.status_code, url, r.text)
                return r.json()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_err = e
            if attempt < cfg.retries:
                logger.warning("POST %s attempt %d/%d failed: %s", url, attempt + 1, cfg.retries + 1, e)
    raise last_err  # type: ignore


async def _put(url: str, payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=cfg.timeout_s) as client:
        r = await client.put(url, json=payload)
        if r.status_code >= 400:
            raise MosaicHTTPError(r.status_code, url, r.text)
        return r.json()


async def _delete(url: str) -> Any:
    async with httpx.AsyncClient(timeout=cfg.timeout_s) as client:
        r = await client.delete(url)
        if r.status_code >= 400:
            raise MosaicHTTPError(r.status_code, url, r.text)
        try:
            return r.json()
        except Exception:
            return {"ok": True}


def _err(e: Exception, context: str) -> dict:
    """Convert an exception into a standard error dict."""
    if isinstance(e, MosaicHTTPError):
        return {"error": True, "context": context, "http_status": e.status, "detail": e.body[:300]}
    return {"error": True, "context": context, "detail": str(e)}
