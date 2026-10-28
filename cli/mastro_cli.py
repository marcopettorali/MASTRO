#!/usr/bin/env python3
"""mastro — Command Line Interface for the MASTRO platform.

Covers the REST surface of both backends:
  * MASTRO (agentic modules): MCP Gateway control, agents & skills,
    LLM/Mongo/notification configuration, intent submission (SSE),
    sessions, autonomous loop, notifications and operational context;
  * Managed orchestrator: commands supplied by the replaceable adapter.
Each command is sent to the backend it belongs to.

The command is installed as `mastro`.

Configuration (resolution order, for each backend):
  MASTRO: --url,        MASTRO_URL, ~/.mastro/config.json "url",        default http://127.0.0.1:9100
  Orchestrator: --orchestrator-url, ORCHESTRATOR_URL, config "orchestrator_url", adapter default

Conventions:
  -q KEY=VALUE   repeatable, adds query-string parameters
  -d JSON|@file  request body for POST/PUT/DELETE (JSON string or @path)
  --form K=V     repeatable, multipart form field (upload commands)
  --file K=PATH  repeatable, multipart file field (upload commands)

Exit codes: 0 success · 1 HTTP/connection error · 2 usage error · 3 agent error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Source checkout and installed CLI use the same replaceable adapter package.
_project_root = Path(__file__).resolve().parents[1]
if (_project_root / "orchestrator").is_dir():
    sys.path.insert(0, str(_project_root))
import orchestrator as adapter

try:
    import httpx
except ImportError:
    print("error: the 'httpx' package is required ->  pip install httpx", file=sys.stderr)
    sys.exit(2)

CONFIG_PATH = Path.home() / ".mastro" / "config.json"
DEFAULT_URL = "http://127.0.0.1:9100"         # MASTRO backend


# Command groups served by the MASTRO backend; every other group belongs to the adapter.
MASTRO_GROUPS = {"mcp", "agent", "skill", "llm", "mongo", "sessions",
                 "autonomous", "context", "notifications", "intent"}
DEFAULT_TIMEOUT = 30.0


# ───────────────────────────── local config ─────────────────────────────────

def load_local_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_local_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def resolve_url(args, target: str = "mastro") -> str:
    """Base URL of the *target* backend ("mastro" or "orchestrator")."""
    if target == "orchestrator":
        return adapter.resolve_cli_url(args, load_local_config())
    else:
        flag, env, key, default = "url", "MASTRO_URL", "url", DEFAULT_URL
    if getattr(args, flag, None):
        return getattr(args, flag).rstrip("/")
    if os.environ.get(env):
        return os.environ[env].rstrip("/")
    return load_local_config().get(key, default).rstrip("/")


# ───────────────────────────── HTTP helpers ─────────────────────────────────

def parse_kv(pairs: list[str] | None, what: str) -> dict:
    out = {}
    for p in pairs or []:
        if "=" not in p:
            print(f"error: invalid {what} '{p}', expected KEY=VALUE", file=sys.stderr)
            sys.exit(2)
        k, v = p.split("=", 1)
        out[k] = v
    return out


def parse_body(data: str | None):
    if data is None:
        return None
    raw = data
    if data.startswith("@"):
        try:
            raw = Path(data[1:]).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot read body file: {exc}", file=sys.stderr)
            sys.exit(2)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: body is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)


def emit(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def request(args, method: str, path: str, *, params=None, body=None,
            form=None, files=None, target: str = "mastro") -> int:
    base = resolve_url(args, target)
    timeout = getattr(args, "timeout", None) or DEFAULT_TIMEOUT
    opened = []
    try:
        kwargs: dict = {"params": params or None}
        if files or form:
            file_map = {}
            for field, fpath in (files or {}).items():
                fh = open(fpath, "rb")
                opened.append(fh)
                file_map[field] = (Path(fpath).name, fh)
            kwargs["data"] = form or None
            kwargs["files"] = file_map or None
        elif body is not None:
            kwargs["json"] = body
        resp = httpx.request(method, base + path, timeout=timeout, **kwargs)
    except httpx.HTTPError as exc:
        print(f"error: cannot reach {target.upper()} backend at {base}: {exc}", file=sys.stderr)
        return 1
    finally:
        for fh in opened:
            fh.close()

    try:
        payload = resp.json()
    except ValueError:
        payload = {"raw": resp.text}
    emit(payload)
    return 0 if resp.status_code < 400 else 1


# ───────────────────────────── intent (SSE) ─────────────────────────────────

def cmd_intent(args) -> int:
    base = resolve_url(args)
    payload = {"message": args.message, "agent_id": args.agent}
    if args.session:
        payload["session_id"] = args.session

    tokens: list[str] = []
    steps: list[dict] = []
    session_id = args.session
    n_steps = 0
    context_ids: list[str] = []
    error: str | None = None

    try:
        with httpx.Client(timeout=httpx.Timeout(args.timeout or 300.0)) as client:
            with client.stream("POST", base + "/api/intent/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    print(f"error: backend returned HTTP {resp.status_code}", file=sys.stderr)
                    return 1
                session_id = resp.headers.get("X-Session-Id", session_id)
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    try:
                        evt = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    etype = evt.get("type")
                    if etype == "token":
                        tokens.append(evt.get("content", ""))
                        if not args.json:
                            print(evt.get("content", ""), end="", flush=True)
                    elif etype in ("thought", "action", "observation"):
                        steps.append(evt)
                        if args.trace and not args.json:
                            tag = etype.upper()
                            content = evt.get("content") or \
                                f"{evt.get('tool', '')} {json.dumps(evt.get('args', {}), ensure_ascii=False)}"
                            print(f"[{tag}] {content}", file=sys.stderr)
                    elif etype == "warning":
                        print(f"[WARNING] {evt.get('message', '')}", file=sys.stderr)
                    elif etype == "error":
                        error = evt.get("message", "unknown agent error")
                    elif etype == "done":
                        n_steps = evt.get("steps", len(steps))
                        context_ids = evt.get("context_ids", [])
    except httpx.HTTPError as exc:
        print(f"error: cannot reach MASTRO backend at {base}: {exc}", file=sys.stderr)
        return 1

    answer = "".join(tokens).strip()
    if args.json:
        emit({"session_id": session_id, "answer": answer,
              "steps": n_steps, "reasoning_steps": steps,
              "context_ids": context_ids, "error": error})
    else:
        if answer:
            print()
        if session_id:
            print(f"(session: {session_id})", file=sys.stderr)
    if error:
        if not args.json:
            print(f"[ERROR] {error}", file=sys.stderr)
        return 3
    return 0


# ───────────────────────────── command registry ─────────────────────────────
# (group, sub, method, path, help)  — {placeholders} become positional args.

SPEC: list[tuple[str, str | None, str, str, str]] = [
    # MCP Gateway control
    ("mcp",      "status",        "GET",  "/api/mcp/status",              "MASTRO MCP Gateway status"),
    ("mcp",      "logs",          "GET",  "/api/mcp/logs",                "MASTRO MCP Gateway logs"),
    ("mcp",      "nodes",         "GET",  "/api/mcp/nodes",               "Nodes known to the MCP Gateway"),
    ("mcp",      "start",         "POST", "/api/mcp/start",               "Start the MASTRO MCP Gateway"),
    ("mcp",      "stop",          "POST", "/api/mcp/stop",                "Stop the MASTRO MCP Gateway"),
    ("mcp",      "test",          "POST", "/api/mcp/test",                "Test an MCP server URL (-d '{\"url\": ...}')"),
    # Agents & skills
    ("agent",    "list",          "GET",  "/api/agents",                  "List configured agents"),
    ("agent",    "get",           "GET",  "/api/agents/{agent_id}",       "Show one agent configuration"),
    ("agent",    "create",        "POST", "/api/agents",                  "Create an agent (-d)"),
    ("agent",    "update",        "PUT",  "/api/agents/{agent_id}",       "Update an agent (-d)"),
    ("agent",    "delete",        "DELETE","/api/agents/{agent_id}",      "Delete an agent"),
    ("skill",    "list",          "GET",  "/api/skills",                  "List skills"),
    ("skill",    "get",           "GET",  "/api/skills/{skill_name}",     "Show a skill document"),
    ("skill",    "create",        "POST", "/api/skills",                  "Create a skill (-d)"),
    ("skill",    "update",        "PUT",  "/api/skills/{skill_name}",     "Update a skill (-d)"),
    ("skill",    "delete",        "DELETE","/api/skills/{skill_name}",    "Delete a skill"),
    # Platform configuration
    ("llm",      "get",           "GET",  "/api/config/llm",              "Show default LLM settings"),
    ("llm",      "set",           "POST", "/api/config/llm",              "Save default LLM settings (-d)"),
    ("mongo",    "get",           "GET",  "/api/config/mongodb",          "Show MongoDB configuration"),
    ("mongo",    "set",           "POST", "/api/config/mongodb",          "Save MongoDB configuration (-d)"),
    ("mongo",    "test",          "POST", "/api/config/mongodb/test",     "Test a MongoDB connection (-d)"),
    # Sessions
    ("sessions", "list",          "GET",  "/api/intent/sessions",         "List chat/autonomous sessions (-q agent_id=, -q limit=)"),
    ("sessions", "get",           "GET",  "/api/intent/sessions/{session_id}", "Show one session with messages"),
    ("sessions", "delete",        "DELETE","/api/intent/sessions/{session_id}", "Delete a session"),
    # Autonomous loop
    ("autonomous","status",       "GET",  "/api/autonomous/status",       "Status of autonomous loops (last tick, last verdict)"),
    ("autonomous","tick",         "POST", "/api/autonomous/{agent_id}/tick", "Trigger one autonomous tick now"),
    ("autonomous","history",      "GET",  "/api/autonomous/{agent_id}/history", "Tick history, newest first (-q limit=N)"),
    # Operational context (exogenous facts/goals injected into agent prompts)
    ("context",  "list",          "GET",  "/api/context",                 "List operational context entries (-q include_history=false, -q limit=N)"),
    ("context",  "types",         "GET",  "/api/context/types",           "List supported context entry types and their default mode"),
    ("context",  "add",           "POST", "/api/context",                 "Add a context entry (-d '{\"type\": ..., \"summary\": ..., \"source\": ..., \"valid_until\": ...}')"),
    ("context",  "enable",        "POST", "/api/context/{entry_id}/enable",  "Re-enable a disabled context entry"),
    ("context",  "disable",       "POST", "/api/context/{entry_id}/disable", "Disable a context entry without revoking it (reversible)"),
    ("context",  "revoke",        "POST", "/api/context/{entry_id}/revoke",  "Revoke a context entry (kept in history, never deleted)"),
    # Notifications
    ("notifications","list",      "GET",  "/api/notifications",           "List notifications (-q unread_only=true, -q limit=N)"),
    ("notifications","read",      "POST", "/api/notifications/{notif_id}/read", "Mark a notification as read"),
    ("notifications","read-all",  "POST", "/api/notifications/read-all",  "Mark all notifications as read"),
    ("notifications","config",    "GET",  "/api/config/notifications",    "Show notifications webhook configuration"),
    ("notifications","config-set","POST", "/api/config/notifications",    "Save webhook configuration (-d '{\"webhook_url\": ...}')"),
    ("notifications","test",      "POST", "/api/config/notifications/test","Send a test push (-d '{\"webhook_url\": ...}')"),
]

PLACEHOLDER_HELP = {
    "agent_id": "Agent identifier (see: mastro agent list)",
    "skill_name": "Skill name (see: mastro skill list)",
    "session_id": "Session identifier (see: mastro sessions list)",
    "notif_id": "Notification identifier (see: mastro notifications list)",
    "entry_id": "Context entry identifier (see: mastro context list)",
}


def make_handler(method: str, path: str, target: str):
    import re
    placeholders = re.findall(r"{(\w+)}", path)

    def handler(args) -> int:
        real_path = path
        for ph in placeholders:
            real_path = real_path.replace("{" + ph + "}", getattr(args, ph))
        params = parse_kv(getattr(args, "query", None), "query parameter")
        body = parse_body(getattr(args, "data", None)) if method != "GET" else None
        form = parse_kv(getattr(args, "form", None), "form field") if method != "GET" else None
        files = parse_kv(getattr(args, "file", None), "file field") if method != "GET" else None
        return request(args, method, real_path, params=params,
                       body=body, form=form or None, files=files or None, target=target)
    return handler, placeholders


# ───────────────────────────── parser assembly ──────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    import re
    parser = argparse.ArgumentParser(
        prog="mastro",
        description="CLI for MASTRO and its configured orchestrator.",
        epilog="Run 'mastro <group> --help' for the sub-commands of each group.",
    )
    parser.add_argument("--url", help="MASTRO backend base URL (overrides MASTRO_URL and config file)")
    parser.add_argument("--orchestrator-url", help="Managed orchestrator base URL")
    adapter.configure_cli(parser)
    parser.add_argument("--timeout", type=float, help=f"Request timeout in seconds (default {DEFAULT_TIMEOUT:g})")
    top = parser.add_subparsers(dest="command", metavar="<command>")

    def add_common(p, method):
        p.add_argument("-q", "--query", action="append", metavar="K=V",
                       help="query-string parameter (repeatable)")
        if method != "GET":
            p.add_argument("-d", "--data", metavar="JSON|@file", help="JSON request body")
            p.add_argument("--form", action="append", metavar="K=V", help="multipart form field (repeatable)")
            p.add_argument("--file", action="append", metavar="K=PATH", help="multipart file field (repeatable)")

    groups: dict[str, argparse._SubParsersAction] = {}
    for group, sub, method, path, help_text in [*SPEC, *adapter.cli_commands()]:
        handler, placeholders = make_handler(method, path, "mastro" if group in MASTRO_GROUPS else "orchestrator")
        if sub is None:
            p = top.add_parser(group, help=help_text, description=help_text)
        else:
            if group not in groups:
                gp = top.add_parser(group, help=f"{group} commands")
                groups[group] = gp.add_subparsers(dest="subcommand", metavar="<subcommand>", required=True)
            p = groups[group].add_parser(sub, help=help_text, description=help_text)
        for ph in placeholders:
            p.add_argument(ph, help=PLACEHOLDER_HELP.get(ph, ph))
        add_common(p, method)
        p.set_defaults(func=handler)

    # intent (curated, SSE)
    p_intent = top.add_parser("intent", help="Submit a natural-language intent to a MASTRO agent",
                              description="Submit an intent and stream the agent's answer (ReAct loop).")
    p_intent.add_argument("message", help="The intent, in natural language")
    p_intent.add_argument("--agent", required=True, help="Agent identifier (see: mastro agent list)")
    p_intent.add_argument("--session", help="Continue an existing session")
    p_intent.add_argument("--trace", action="store_true", help="Print the ReAct trace (thought/action/observation) to stderr")
    p_intent.add_argument("--json", action="store_true", help="Emit a single JSON object instead of streaming text")
    p_intent.set_defaults(func=cmd_intent)

    # local CLI config
    p_cfg = top.add_parser("config", help="Local CLI configuration (~/.mastro/config.json)")
    cfg_sub = p_cfg.add_subparsers(dest="subcommand", metavar="<subcommand>", required=True)
    p_show = cfg_sub.add_parser("show", help="Show the resolved backend URLs and config file")
    p_show.set_defaults(func=lambda a: (emit({"url": resolve_url(a, "mastro"),
                                              "orchestrator_url": resolve_url(a, "orchestrator"),
                                              "config_file": str(CONFIG_PATH),
                                              "config_file_exists": CONFIG_PATH.exists()}) or 0))

    def _setter(key: str):
        def _set(a):
            cfg = load_local_config(); cfg[key] = a.backend_url.rstrip("/")
            save_local_config(cfg); emit({"ok": True, key: cfg[key]}); return 0
        return _set
    p_set = cfg_sub.add_parser("set-url", help="Persist the MASTRO backend URL")
    p_set.add_argument("backend_url", help="e.g. http://mastro-host:9100")
    p_set.set_defaults(func=_setter("url"))
    p_set_m = cfg_sub.add_parser("set-orchestrator-url", help="Persist the managed orchestrator URL")
    p_set_m.add_argument("backend_url", help="Managed orchestrator base URL")
    p_set_m.set_defaults(func=_setter("orchestrator_url"))

    adapter.configure_cli_config(cfg_sub, _setter)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except BrokenPipeError:
        # Downstream consumer (e.g. head, grep -m) closed the pipe: not an error.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
