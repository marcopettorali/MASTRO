"""In-memory run manager that decouples ReAct execution from the SSE connection.

A "run" is a single ReAct turn. The execution happens in a detached asyncio task
(see routers/intent.py::_execute_run) that publishes SSE chunks into an append-only
buffer; one or more clients subscribe to that buffer to observe the run.

If a client disconnects — e.g. the operator leaves the chat page — only the
subscriber coroutine is cancelled. The background task keeps running to completion
and persists its result regardless. A client that comes back can replay the buffer
and resume the live stream via /api/intent/stream/{run_id}.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncGenerator

# How long a finished run stays available for late reconnection / replay.
RUN_TTL_SECONDS = 600        # 10 minutes
# Hard cap on how many finished runs we keep in memory.
MAX_FINISHED_RUNS = 50


class RunState:
    """State of a single ReAct turn shared between its executor and its observers."""

    def __init__(self, run_id: str, session_id: str, agent_id: str, user_message: str):
        self.run_id = run_id
        self.session_id = session_id
        self.agent_id = agent_id
        self.user_message = user_message
        self.buffer: list[str] = []          # append-only list of raw SSE chunks
        self.status: str = "running"         # running | done | error
        self.created_at: float = time.time()
        self.finished_at: float | None = None
        self.task: asyncio.Task | None = None
        self._cond = asyncio.Condition()

    async def publish(self, chunk: str) -> None:
        """Append an SSE chunk to the buffer and wake all subscribers."""
        async with self._cond:
            self.buffer.append(chunk)
            self._cond.notify_all()

    async def finish(self, status: str = "done") -> None:
        """Mark the run terminal and wake subscribers so they can drain and exit."""
        async with self._cond:
            self.status = status
            self.finished_at = time.time()
            self._cond.notify_all()

    async def stream(self) -> AsyncGenerator[str, None]:
        """Replay the buffer from the start, then yield live chunks until the run ends.

        Race-free: buffer reads and the terminal-status check happen under the same
        lock, so no chunk can slip between replay and live subscription. Cancelling
        this generator (client disconnect) never affects the underlying run.
        """
        cursor = 0
        while True:
            async with self._cond:
                while cursor >= len(self.buffer) and self.status == "running":
                    await self._cond.wait()
                new_chunks = self.buffer[cursor:]
                cursor = len(self.buffer)
                finished = self.status != "running"
            for chunk in new_chunks:
                yield chunk
            if finished and cursor >= len(self.buffer):
                break


class RunManager:
    """Registry of active and recently-finished runs."""

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._active_by_session: dict[str, str] = {}

    def _gc(self) -> None:
        """Drop finished runs older than the TTL, then enforce the hard cap."""
        now = time.time()
        for rid in [
            r.run_id for r in list(self._runs.values())
            if r.status != "running" and r.finished_at and now - r.finished_at > RUN_TTL_SECONDS
        ]:
            self._runs.pop(rid, None)

        finished = sorted(
            [r for r in self._runs.values() if r.status != "running"],
            key=lambda r: r.finished_at or 0.0,
        )
        while len(finished) > MAX_FINISHED_RUNS:
            victim = finished.pop(0)
            self._runs.pop(victim.run_id, None)

    def create(self, session_id: str, agent_id: str, user_message: str) -> RunState:
        self._gc()
        run = RunState(str(uuid.uuid4()), session_id, agent_id, user_message)
        self._runs[run.run_id] = run
        self._active_by_session[session_id] = run.run_id
        return run

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def active_for_session(self, session_id: str) -> RunState | None:
        """Return the run still in progress for a session, or None."""
        rid = self._active_by_session.get(session_id)
        if not rid:
            return None
        run = self._runs.get(rid)
        if run and run.status == "running":
            return run
        return None


# Module-level singleton shared by the intent router.
run_manager = RunManager()
