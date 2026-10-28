"""MASTRO LLM Adapter — OpenAI-compatible API via httpx.

Supports any endpoint that speaks the OpenAI /chat/completions protocol:
  - OpenAI (api.openai.com)
  - Ollama  (http://localhost:11434/v1)
  - vLLM    (http://localhost:8000/v1)
  - LM Studio, LocalAI, etc.

The adapter provides two methods:
  chat()   — non-streaming, returns full ChatResponse
  stream() — async generator of token strings (final answer only)
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

import httpx

logger = logging.getLogger("mastro.llm")


class LLMError(Exception):
    pass


class ChatResponse:
    def __init__(self, content: str | None, tool_calls: list[dict] | None, raw: dict):
        self.content = content or ""
        self.tool_calls = tool_calls or []
        self.raw = raw

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMAdapter:
    """Thin wrapper around any OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, settings: dict):
        self.base_url: str = settings.get("base_url", "http://localhost:11434/v1").rstrip("/")
        self.model: str = settings.get("model", "qwen2.5:32b")
        self.api_key: str = settings.get("api_key", "ollama")
        self.temperature: float = float(settings.get("temperature", 0.2))
        self.max_tokens: int = int(settings.get("max_tokens", 2048))
        self.timeout: float = float(settings.get("timeout_s", 120.0))

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _base_payload(self, messages: list[dict], tools: list[dict] | None) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    # ------------------------------------------------------------------
    # Non-streaming call — used during ReAct think/act steps
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> ChatResponse:
        payload = self._base_payload(messages, tools)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.RequestError as exc:
            raise LLMError(f"Request error: {exc}") from exc

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        raw_tool_calls = message.get("tool_calls") or []

        tool_calls = []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": args,
            })

        return ChatResponse(content=content, tool_calls=tool_calls, raw=data)

    # ------------------------------------------------------------------
    # Streaming call — used for the final answer
    # ------------------------------------------------------------------

    async def stream(
        self,
        messages: list[dict],
    ) -> AsyncGenerator[str, None]:
        payload = self._base_payload(messages, tools=None)
        payload["stream"] = True

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                            delta = chunk["choices"][0].get("delta", {})
                            token = delta.get("content") or ""
                            if token:
                                yield token
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except httpx.RequestError as exc:
            raise LLMError(f"Stream error: {exc}") from exc
