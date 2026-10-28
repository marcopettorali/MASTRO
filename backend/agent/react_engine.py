"""ReAct Engine — Reason + Act loop with SSE streaming.

Supports two execution modes, selected automatically:
  - Native function calling: model returns proper tool_calls (OpenAI format)
  - Text ReAct fallback:     model outputs Action/Action Input in text or JSON

No autonomous ticking: the loop runs only when triggered by a user message.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import AsyncGenerator

from .llm_adapter import LLMAdapter, LLMError
from . import mcp_bridge
from .skill_loader import load_skills
from ..context_store import context_store

logger = logging.getLogger("mastro.react")

MAX_STEPS = 10

# Cap the size of a single tool observation *as fed back to the LLM*. Some tools
# (e.g. get_jobs) can return hundreds of KB because they embed per-step
# job payloads; left uncapped, a single observation overflows the model context on
# the next step. The full observation is still emitted in the SSE stream and stored
# in reasoning_steps for inspection — only the copy sent to the model is truncated.
MAX_OBSERVATION_CHARS = 8000


def _truncate_observation(text: str) -> str:
    if text is None:
        return ""
    if len(text) <= MAX_OBSERVATION_CHARS:
        return text
    head = text[:MAX_OBSERVATION_CHARS]
    return (
        head
        + f"\n\n[...truncated {len(text) - MAX_OBSERVATION_CHARS} chars of {len(text)} total. "
        "Use a more specific tool or arguments if you need the omitted detail.]"
    )


def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"


# ── Text-based ReAct parser ────────────────────────────────────────────────────

def _parse_text_tool_call(content: str) -> dict | None:
    """Parse a tool call from model text output.

    Handles three common formats models use when function calling isn't native:

    1. JSON block:
       {"tool": "get_jobs", "arguments": {}}
       {"action": "get_jobs", "action_input": {"node_id": "fog-1"}}

    2. ReAct text format:
       Thought: I need to check...
       Action: get_jobs
       Action Input: {}

    3. Markdown code block containing JSON:
       ```json
       {"tool": "get_jobs", "arguments": {}}
       ```
    """
    if not content:
        return None

    # ── 1. Extract from markdown code block ───────────────────────────────
    block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if block_match:
        content_to_parse = block_match.group(1)
    else:
        content_to_parse = content

    # ── 2. Try JSON object with "tool" or "action" key ────────────────────
    json_match = re.search(r"\{[^{}]*(?:\"tool\"|\"action\")[^{}]*\}", content_to_parse, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            tool_name = data.get("tool") or data.get("action") or data.get("function")
            if tool_name:
                args = (
                    data.get("arguments")
                    or data.get("action_input")
                    or data.get("input")
                    or data.get("parameters")
                    or {}
                )
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                return {"name": str(tool_name), "arguments": args if isinstance(args, dict) else {}}
        except json.JSONDecodeError:
            pass

    # ── 3. ReAct text format ───────────────────────────────────────────────
    action_match = re.search(r"(?:^|\n)Action\s*:\s*([^\n]+)", content, re.IGNORECASE)
    if action_match:
        tool_name = action_match.group(1).strip()
        args: dict = {}
        input_match = re.search(r"Action\s*Input\s*:\s*(\{.*?\})", content, re.DOTALL | re.IGNORECASE)
        if input_match:
            try:
                args = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                args = {}
        return {"name": tool_name, "arguments": args}

    return None


def _is_final_answer(content: str) -> bool:
    """Return True if the content looks like a Final Answer (not a tool call)."""
    if not content or not content.strip():
        return False
    markers = ["final answer:", "final answer :", "risposta finale:"]
    lower = content.lower()
    return any(lower.lstrip().startswith(m) for m in markers)


def _strip_final_answer_prefix(content: str) -> str:
    return re.sub(r"(?i)^.*?final answer\s*:\s*", "", content, count=1).strip()


# ── Main ReAct loop ────────────────────────────────────────────────────────────

async def run(
    *,
    session_id: str,
    agent_config: dict,
    conversation_history: list[dict],
    user_message: str,
    llm_settings: dict,
    mcp_url: str,
    skills_dir,
) -> AsyncGenerator[str, None]:
    """Run a single conversational ReAct turn and yield SSE events."""

    # ── 1. Build system prompt ─────────────────────────────────────────────
    base_prompt = agent_config.get("system_prompt", "You are a MASTRO agent operating managed infrastructure.")
    skill_names = agent_config.get("skills", [])
    skill_context = load_skills(skill_names, skills_dir)

    system_content = base_prompt
    if skill_context:
        system_content = base_prompt.rstrip() + "\n\n" + skill_context

    # Operational context (exogenous facts/goals from operator or external
    # coordinator). Injected deterministically at every run — chat turns and
    # autonomous ticks alike — so the agent cannot "forget" to consult it.
    context_block, context_entries = await context_store.build_prompt_block()
    if context_block:
        system_content = system_content.rstrip() + "\n\n" + context_block
    context_ids = [e["_id"] for e in context_entries]

    # ── 2. Fetch MCP tools ─────────────────────────────────────────────────
    tools_raw = await mcp_bridge.list_tools(mcp_url)
    oai_tools = mcp_bridge.to_openai_tools(tools_raw) if tools_raw else []
    tool_names = {t["name"] for t in tools_raw}

    has_native_tools = bool(oai_tools)
    if not has_native_tools:
        yield _sse("warning", {"message": "MCP server unreachable or no tools available. Answering from knowledge only."})

    # ── 3. Build initial message list ─────────────────────────────────────
    # For text-ReAct mode: inject tool list into system prompt
    if has_native_tools:
        final_system = system_content
    else:
        final_system = system_content

    # Inject ReAct text instructions when tool list is available
    # (serves as fallback for models that ignore the tools array)
    if has_native_tools:
        react_hint = (
            "\n\n---\n"
            "You have access to tools via function calling. "
            "Use them when needed to answer accurately. "
            "When you have gathered enough information, provide a clear, "
            "natural language answer to the operator."
        )
        final_system = system_content.rstrip() + react_hint

    messages: list[dict] = [{"role": "system", "content": final_system}]
    for msg in conversation_history[-20:]:
        if msg.get("role") in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    # ── 4. ReAct loop ──────────────────────────────────────────────────────
    adapter = LLMAdapter(llm_settings)
    reasoning_steps: list[dict] = []
    ts = lambda: datetime.now(timezone.utc).isoformat()
    used_fallback = False  # track if we switched to text-ReAct mode
    run_failed = False     # skip context consumption when the run errors out

    try:
        for step in range(1, MAX_STEPS + 1):

            response = await adapter.chat(
                messages,
                tools=oai_tools if has_native_tools else None,
            )

            content = (response.content or "").strip()

            # Per-call token usage (vLLM returns it in the raw response). Logged as
            # a reasoning step so that offline analysis can sum tokens per tick for
            # the energy/efficiency accounting. Pure logging — does not affect the loop.
            _usage = (getattr(response, "raw", None) or {}).get("usage") or {}
            if _usage:
                reasoning_steps.append({
                    "type": "llm_usage", "step": step, "usage": _usage, "timestamp": ts(),
                })

            # ── Detect execution mode ──────────────────────────────────────
            # Mode A: native tool_calls in response
            # Mode B: model output text that encodes a tool call (fallback)
            # Mode C: final answer (no more tool calls needed)

            native_calls = response.tool_calls  # list[dict] | []
            text_call = None

            if not native_calls and content:
                # Check if the model output a text-based tool call
                parsed = _parse_text_tool_call(content)
                if parsed and parsed["name"] in tool_names:
                    text_call = parsed
                    used_fallback = True

            # Build thought content (only meaningful when tool calls follow)
            thought_content = content
            if text_call:
                thought_content = f"[Tool call detected in text output]\n{content}"

            # Emit thought only when the model is reasoning before a tool call,
            # not when it is producing the final answer (no tool calls follow).
            if thought_content and (native_calls or text_call):
                yield _sse("thought", {"step": step, "content": thought_content})
                reasoning_steps.append({
                    "type": "thought", "step": step,
                    "content": thought_content, "timestamp": ts(),
                })

            # ── Mode C: no tool calls → final answer ───────────────────────
            if not native_calls and not text_call:
                final_text = _strip_final_answer_prefix(content) if _is_final_answer(content) else content

                if not final_text:
                    # Empty response — unlikely but handle gracefully
                    yield _sse("token", {"content": "(No response generated)"})
                else:
                    # Emit the already-obtained content as tokens.
                    # Split on whitespace boundaries to give a "streaming" feel
                    # without a second LLM call (which would yield a different answer).
                    for word in re.split(r"(\s+)", final_text):
                        if word:
                            yield _sse("token", {"content": word})
                break

            # ── Mode A: native function calling ───────────────────────────
            if native_calls:
                assistant_msg: dict = {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                        }
                        for tc in native_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in native_calls:
                    yield _sse("action", {"step": step, "tool": tc["name"], "args": tc["arguments"]})
                    reasoning_steps.append({
                        "type": "action", "step": step,
                        "tool": tc["name"], "args": tc["arguments"], "timestamp": ts(),
                    })

                    observation = await mcp_bridge.call_tool(mcp_url, tc["name"], tc["arguments"])

                    yield _sse("observation", {"step": step, "content": observation})
                    reasoning_steps.append({
                        "type": "observation", "step": step,
                        "content": observation, "timestamp": ts(),
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": _truncate_observation(observation),
                    })

            # ── Mode B: text-based fallback ────────────────────────────────
            elif text_call:
                # Treat as if the model had issued a proper tool call
                messages.append({"role": "assistant", "content": content})

                tc_name = text_call["name"]
                tc_args = text_call["arguments"]

                yield _sse("action", {"step": step, "tool": tc_name, "args": tc_args})
                reasoning_steps.append({
                    "type": "action", "step": step,
                    "tool": tc_name, "args": tc_args, "timestamp": ts(),
                })

                observation = await mcp_bridge.call_tool(mcp_url, tc_name, tc_args)

                yield _sse("observation", {"step": step, "content": observation})
                reasoning_steps.append({
                    "type": "observation", "step": step,
                    "content": observation, "timestamp": ts(),
                })

                # Inject observation as user message (text-ReAct convention)
                messages.append({"role": "user", "content": f"Observation: {_truncate_observation(observation)}\nContinue."})

        else:
            yield _sse("warning", {"message": f"Reached max steps ({MAX_STEPS})."})

    except LLMError as exc:
        run_failed = True
        yield _sse("error", {"message": f"LLM error: {exc}"})
    except Exception as exc:
        run_failed = True
        logger.exception("Unexpected error in ReAct loop")
        yield _sse("error", {"message": f"Internal error: {exc}"})

    # ── 5. Context usage accounting ────────────────────────────────────────
    # Recorded at the END of the run, never at injection time: a run that
    # fails midway leaves its one-shot entries active, so they are proposed
    # again to the next run and no operator-declared information is lost.
    if context_entries and not run_failed:
        try:
            await context_store.record_usage(
                context_entries,
                session_id=session_id,
                agent_id=agent_config.get("id", ""),
            )
        except Exception:
            logger.exception("Context usage recording failed")

    yield _sse("done", {
        "session_id": session_id,
        "steps": len([s for s in reasoning_steps if s["type"] == "thought"]),
        "reasoning_steps": reasoning_steps,
        "used_text_fallback": used_fallback,
        "context_ids": context_ids,
    })
