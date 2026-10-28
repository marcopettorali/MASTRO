#!/usr/bin/env python3
"""IntentContinuum implementation control loop: platform-side monitor plus one-shot LLM reconfiguration.
Emulates the PARADIGM of IntentContinuum (Kubernetes/ONOS prototype, GPT-4o) on MOSAIC,
faithfully to its control model and honestly reduced to MOSAIC's action space. It is meant
as a comparison baseline for the MASTRO agents:
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _fname_ts(p):
    m = re.search(r"(\d{8}_\d{6})", os.path.basename(p))
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").replace(
        tzinfo=timezone.utc).timestamp()


class ICDriver(threading.Thread):
    """Background thread implementing the IntentContinuum loop for one run."""

    def __init__(self, *, base_url: str, app: str, services: list[str], nodes: list[str],
                 sla_ms: float, t0: float, duration: float, log_event,
                 llm_settings_path: str = "config/llm_settings.json",
                 poll_s: float = 2.0, sustain_k: int = 3, settle_s: float = 25.0,
                 max_calls: int = 5, stall_s: float | None = None,
                 sustain_for_s: float = 0.0, node_capacities: str | None = None):
        super().__init__(daemon=True, name="ic-driver")
        self.base = base_url.rstrip("/")
        self.app = app
        self.services = services            # counter i+1 -> services[i]; counter 0 = TG
        self.nodes = nodes
        self.sla_ms = float(sla_ms)
        self.t0 = t0
        self.duration = duration
        self.log = log_event
        self.llm_settings_path = llm_settings_path
        self.poll_s = poll_s
        self.sustain_k = sustain_k
        self.settle_s = settle_s
        self.max_calls = max_calls
        self.stall_s = stall_s              # self-healing scenarios: trigger also on completion stall
        # Prometheus-style `for:` clause on the SLA-breach trigger: besides K consecutive
        # over-SLA completions, the violation EPISODE (since its first over-SLA completion)
        # must have lasted at least this long before the alarm fires. 0 = off. Tune it per
        # scenario so that the alarm reflects a sustained violation rather than a transient
        # spike (for example 10 s on the video pipeline, 0 on the audio pipeline).
        self.sustain_for_s = float(sustain_for_s or 0.0)
        # Node capacities as described to the model in the prompt (testbed-specific).
        self.node_capacities = node_capacities or (
            "node01 = 1 vCPU / 1 GB, node02 = 2 vCPU / 2 GB, node03 = 4 vCPU / 4 GB")
        self.s = requests.Session()
        # reasoning trace, scheduler-session shape: ONE message per LLM invocation, so that
        # each attempt counts as one decision, comparable with the agents' per-tick accounting.
        self._messages: list[list[dict]] = []
        self.llm_calls = 0
        self._stop_evt = threading.Event()   # NOT named _stop: would shadow Thread._stop (join() breaks)
        self._perf_csv = None
        self._metrics_csv = None
        self._seen_jobs = 0

    # ── public ────────────────────────────────────────────────────────────────
    def stop(self):
        self._stop_evt.set()

    def reasoning_session(self) -> dict:
        return {"id": f"ic-{int(self.t0)}",
                "paradigm": "intentcontinuum-emulation",
                "messages": [{"reasoning_steps": steps} for steps in self._messages if steps]}

    # ── platform-side monitor (the IC 'intent-aware monitoring') ─────────────
    def _find_csv(self, prefix: str):
        # newest CSV started within 90 s before t0 (the recorders are started just before the
        # traffic generator; 'newest' selects the current session's file because any previous
        # recording stopped before this one started).
        best = None
        for p in glob.glob(f"recordings/**/{prefix}*.csv", recursive=True):
            ts = _fname_ts(p)
            if ts is not None and ts >= self.t0 - 90 and (best is None or ts > _fname_ts(best)):
                best = p
        return best

    def _completed_jobs(self):
        """[(wall_ts, lifetime_ms)] of completed jobs so far, oldest→newest."""
        if not self._perf_csv:
            self._perf_csv = self._find_csv(f"perf_{self.app}_")
        if not self._perf_csv or not os.path.exists(self._perf_csv):
            return []
        rows = []
        try:
            with open(self._perf_csv, encoding="utf-8", errors="replace") as f:
                for r in csv.DictReader(f):
                    if r.get("row_type") != "total" or not r.get("job_lifetime_ms"):
                        continue
                    t = _iso_ts(r.get("recorded_at"))
                    if t is None or t < self.t0 - 2:
                        continue
                    rows.append((t, float(r["job_lifetime_ms"])))
        except Exception:
            return []
        rows.sort(key=lambda x: x[0])
        return rows

    def _node_metrics(self, window_s: float = 30.0):
        """{node: {"cpu_pct": latest, "mem_used_pct": latest,
                   "cpu_avg_window": avg, "samples": n}} from the metrics recorder."""
        if not self._metrics_csv:
            self._metrics_csv = self._find_csv("metrics_")
        out: dict[str, dict] = {}
        if not self._metrics_csv or not os.path.exists(self._metrics_csv):
            return out
        now = time.time()
        try:
            with open(self._metrics_csv, encoding="utf-8", errors="replace") as f:
                for r in csv.DictReader(f):
                    n = r.get("node_id")
                    if not n or not r.get("cpu_pct"):
                        continue
                    t = _iso_ts(r.get("timestamp"))
                    if t is None or t < now - window_s:
                        continue
                    d = out.setdefault(n, {"_cpu": [], "_mem": []})
                    d["_cpu"].append((t, float(r["cpu_pct"])))
                    if r.get("mem_used_pct"):
                        d["_mem"].append((t, float(r["mem_used_pct"])))
        except Exception:
            return {}
        for n, d in out.items():
            cpu = sorted(d.pop("_cpu"))
            mem = sorted(d.pop("_mem"))
            d["cpu_pct"] = round(cpu[-1][1], 1) if cpu else None
            d["mem_used_pct"] = round(mem[-1][1], 1) if mem else None
            d["cpu_avg_window"] = round(sum(v for _, v in cpu) / len(cpu), 1) if cpu else None
            d["samples"] = len(cpu)
            # freshness of the node's telemetry: a dead node's stale samples stay inside the
            # averaging window for up to window_s — liveness must come from THIS, not from
            # mere presence in the window (self-healing scenarios).
            d["last_sample_age_s"] = round(now - cpu[-1][0], 1) if cpu else None
        return out

    def _placement(self) -> dict:
        try:
            resp = self.s.get(self.base + "/api/applications", timeout=30).json()
            apps = resp.get("applications", {})
            if isinstance(apps, dict) and isinstance(apps.get("applications"), dict):
                apps = apps["applications"]
            steps = (apps.get(self.app) or {}).get("steps", [])
            return {int(st["counter"]): st.get("node_id") for st in steps
                    if st.get("counter") is not None}
        except Exception:
            return {}

    # ── snapshot + prompt (the IC 'whole story') ──────────────────────────────
    def _snapshot(self, jobs):
        recent = [round(l, 1) for _, l in jobs[-10:]]
        metrics = self._node_metrics()
        # platform-side liveness: a node is online iff its telemetry is FRESH (a sample in the
        # last 10 s ≈ 10× the recorder period). Mere presence in the 30 s averaging window is
        # NOT enough: a just-killed node keeps stale samples there for up to 30 s.
        statuses = {n: {"ok": (n in metrics
                               and metrics[n].get("last_sample_age_s") is not None
                               and metrics[n]["last_sample_age_s"] < 10.0)}
                    for n in self.nodes}
        return {
            "metrics": metrics,
            "statuses": statuses,
            "placement": {str(k): v for k, v in sorted(self._placement().items())},
            "recent_response_times_ms": recent,
            "sla_ms": self.sla_ms,
            "completed_jobs": len(jobs),
        }

    def _build_prompt(self, snapshot: dict, attempt: int, tried: list) -> str:
        svc_lines = "\n".join(
            f"  - counter {i + 1}: service '{s}'" for i, s in enumerate(self.services))
        feedback = ""
        if attempt > 1:
            feedback = (
                f"\nThis is attempt {attempt}: the previous recommended action(s) "
                f"{json.dumps(tried)} did NOT resolve the violation (the response time is "
                "still above the maximum threshold). Try another approach.\n")
        template = json.dumps({
            "Source of Violation": {
                "Reason": [
                    {"description": "high_cpu_utilization_on_nodes", "details": {"nodes": [""]}},
                    {"description": "high_cpu_utilization_on_services", "details": {"services": [""]}},
                    {"description": "node_offline", "details": {"nodes": [""]}},
                    {"description": "Unknown_Reason", "details": {"description": ""}},
                ]
            },
            "Recommended Action": {
                "current_placement": [{"counter": "counter_number", "node": "node_name"}],
                "new_placement": [{"counter": "counter_number", "node_id": "node_name"}],
            },
        }, indent=4)
        return (
            "There is a MOSAIC edge cluster with a distributed application running as a linear "
            "pipeline of steps on the nodes. There is an objective (intent) from the user. The "
            "intent is \"application response time\". This intent has to always be below a maximum "
            "threshold. Now the intent is violated since it is greater than the maximum threshold.\n"
            "All the details about the system along with the monitoring data during the violation "
            "are provided below for analysis. You need to find the root cause of the violation as "
            "well as the actions that can be taken to solve the issue.\n\n"
            "SYSTEM DESCRIPTION:\n"
            f"- Nodes and capacities: {self.node_capacities}.\n"
            f"- Application '{self.app}': linear chain of steps identified by a counter. "
            "Counter 0 is the traffic generator (the load source).\n"
            f"{svc_lines}\n"
            "- The only reconfiguration available is changing the placement of a step "
            "(assigning its counter to another node). Counter 0 can NEVER be moved.\n\n"
            f"INTENT: end-to-end response time <= {self.sla_ms / 1000.0:.1f} s "
            f"(maximum threshold = {self.sla_ms:.0f} ms).\n\n"
            "MONITORING DATA (collected at the violation):\n"
            f"{json.dumps(snapshot, indent=2)}\n"
            f"{feedback}\n"
            "What could be the potential root cause and what actions should be taken to mitigate "
            "this issue?\n\n"
            "Please provide your response in a single complete JSON format containing all "
            "recommended actions.\n\n"
            f"FORCED_TEMPLATE:\n{template}\n\n"
            "Fill ONLY the reasons that apply (leave the others with empty values). "
            "try to provide optimized answer with the minimal changes and provide the most "
            "relevant action. No explanation is needed, the reply should have the template only. "
            "Make sure that addressing this violation is not causing a new violation elsewhere."
        )

    # ── LLM (same endpoint/model/settings as the MASTRO agents: llm_settings.json) ──
    def _llm(self, prompt: str):
        cfg = json.loads(Path(self.llm_settings_path).read_text(encoding="utf-8"))
        body = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": int(cfg.get("max_tokens", 2048)),
            "temperature": float(cfg.get("temperature", 0.2)),
            "n": 1,
        }
        headers = {"Authorization": f"Bearer {cfg.get('api_key', '')}"}
        t_start = time.time()
        r = self.s.post(cfg["base_url"].rstrip("/") + "/chat/completions",
                        json=body, headers=headers,
                        timeout=float(cfg.get("timeout_s", 120)))
        r.raise_for_status()
        data = r.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        usage = data.get("usage") or {}
        return text.strip(), usage, time.time() - t_start

    @staticmethod
    def _parse_actions(text: str):
        """Extract Recommended Action.new_placement from the (possibly fenced) JSON reply."""
        raw = text.strip()
        raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw, flags=re.S)
        start = raw.find("{")
        if start < 0:
            return None, "no JSON object in reply"
        depth = 0
        end = None
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            return None, "unbalanced JSON in reply"
        try:
            obj = json.loads(raw[start:end])
        except ValueError as exc:
            return None, f"JSON parse error: {exc}"
        act = (obj.get("Recommended Action") or {})
        moves = act.get("new_placement") or []
        out = []
        for m in moves:
            if not isinstance(m, dict):
                continue
            try:
                c = int(m.get("counter"))
            except (TypeError, ValueError):
                continue
            n = m.get("node_id") or m.get("node")
            if isinstance(n, str):
                out.append({"counter": c, "node_id": n.strip()})
        return {"root_cause": obj.get("Source of Violation"), "moves": out}, None

    # ── apply (same backend path as mosaic_set_placement: hot reload + rewire) ─
    def _apply(self, moves: list[dict]):
        resp = self.s.get(self.base + "/api/applications", timeout=60).json()
        apps = resp.get("applications", {})
        if isinstance(apps, dict) and isinstance(apps.get("applications"), dict):
            apps = apps["applications"]
        if self.app not in apps:
            raise RuntimeError(f"app {self.app} not in map")
        steps = apps[self.app].get("steps", [])
        amap = {m["counter"]: m["node_id"] for m in moves}
        for st in steps:
            c = st.get("counter")
            if c in amap:
                st["node_id"] = amap[c]
        counters = [s.get("counter") for s in steps]
        if (all(isinstance(c, int) for c in counters) and len(set(counters)) == len(counters)
                and sorted(counters) == list(range(min(counters), max(counters) + 1))):
            ordered = sorted(steps, key=lambda s: s["counter"])
            for i, st in enumerate(ordered):
                st["forward_to"] = ([{"node_id": ordered[i + 1]["node_id"]}]
                                    if i < len(ordered) - 1 else [])
        apps[self.app]["steps"] = steps
        r = self.s.post(self.base + "/api/save-applications",
                        json={"applications": {"applications": apps}}, timeout=60)
        r.raise_for_status()
        r = self.s.post(self.base + "/api/deploy-plan-files-for-application",
                        json={"application_name": self.app, "restart_api": False}, timeout=120)
        r.raise_for_status()

    # ── trace helpers (scheduler-session-compatible steps) ────────────────────
    def _new_message(self):
        self._messages.append([])

    def _step(self, typ: str, **kw):
        if not self._messages:
            self._messages.append([])
        self._messages[-1].append({"timestamp": _now_iso(), "type": typ, **kw})

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self):
        self.log("ic_driver_started", sla_ms=self.sla_ms, sustain_k=self.sustain_k,
                 sustain_for_s=self.sustain_for_s, settle_s=self.settle_s,
                 max_calls=self.max_calls, stall_s=self.stall_s, poll_s=self.poll_s)
        tried: list = []
        settle_until = 0.0
        last_completion_wall = self.t0
        while not self._stop_evt.is_set() and (time.time() - self.t0) < self.duration:
            time.sleep(self.poll_s)
            now = time.time()
            if now < settle_until:
                continue
            jobs = self._completed_jobs()
            if jobs:
                last_completion_wall = jobs[-1][0]
            # trigger 1: K consecutive completed jobs above the SLA, AND (`for:` clause)
            # the violation episode old enough — see sustain_for_s in __init__.
            suffix = 0
            for _, l in reversed(jobs):
                if l > self.sla_ms:
                    suffix += 1
                else:
                    break
            episode_start = jobs[len(jobs) - suffix][0] if suffix else None
            breach = (suffix >= self.sustain_k and jobs[-1][0] > self.t0
                      and (self.sustain_for_s <= 0
                           or (episode_start is not None
                               and (now - episode_start) >= self.sustain_for_s)))
            # trigger 2 (self-healing scenarios): completions stalled entirely
            stall = (self.stall_s is not None
                     and (now - last_completion_wall) > self.stall_s
                     and (now - self.t0) > self.stall_s)
            if not (breach or stall):
                continue
            if self.llm_calls >= self.max_calls:
                self.log("ic_call_budget_exhausted", calls=self.llm_calls)
                break
            attempt = self.llm_calls + 1
            elapsed = round(now - self.t0, 3)
            self.log("ic_violation_detected", elapsed_s=elapsed,
                     trigger=("stall" if stall and not breach else "sla_breach"),
                     last_rts=[round(l) for _, l in jobs[-self.sustain_k:]],
                     episode_age_s=(round(now - episode_start, 1) if episode_start else None),
                     attempt=attempt)
            self._new_message()          # one message (-> one tick) per LLM invocation
            snapshot = self._snapshot(jobs)
            if stall and not breach:
                snapshot["completion_stall_s"] = round(now - last_completion_wall, 1)
            # observation step at the DETECTION instant (detection time reference)
            self._step("observation", tool="ic_platform_monitor",
                       content=json.dumps(snapshot))
            prompt = self._build_prompt(snapshot, attempt, tried)
            try:
                text, usage, lat = self._llm(prompt)
            except Exception as exc:
                self.log("ic_llm_error", error=str(exc)[:200], attempt=attempt)
                settle_until = time.time() + self.settle_s
                continue
            self.llm_calls += 1
            self._step("llm_usage", tool="chat.completions",
                       usage={"prompt_tokens": usage.get("prompt_tokens", 0),
                              "completion_tokens": usage.get("completion_tokens", 0),
                              "total_tokens": usage.get("total_tokens", 0)})
            self.log("ic_llm_call", attempt=attempt, latency_s=round(lat, 2),
                     prompt_tokens=usage.get("prompt_tokens"),
                     completion_tokens=usage.get("completion_tokens"))
            parsed, err = self._parse_actions(text)
            if err or parsed is None:
                self.log("ic_parse_error", error=err, reply_head=text[:150], attempt=attempt)
                self._step("thought", content=f"unparseable reply: {err}")
                settle_until = time.time() + self.settle_s
                continue
            moves = [m for m in parsed["moves"]
                     if m["counter"] != 0 and m["node_id"] in self.nodes]
            dropped = [m for m in parsed["moves"] if m not in moves]
            if dropped:
                self.log("ic_moves_dropped", dropped=dropped, attempt=attempt)
            cur = self._placement()
            moves = [m for m in moves if cur.get(m["counter"]) != m["node_id"]]
            if not moves:
                self.log("ic_no_action", attempt=attempt,
                         root_cause=json.dumps(parsed.get("root_cause"))[:180])
                self._step("thought", content="LLM recommended no applicable placement change")
                settle_until = time.time() + self.settle_s
                continue
            try:
                self._apply(moves)
                # action step (actuation time reference; same tool name used by the agents)
                self._step("action", tool="mosaic_set_placement",
                           content=json.dumps({"step_assignments": moves,
                                               "root_cause": parsed.get("root_cause")}))
                tried.append(moves)
                self.log("ic_action_applied", moves=moves, attempt=attempt,
                         elapsed_s=round(time.time() - self.t0, 3))
            except Exception as exc:
                self.log("ic_apply_error", error=str(exc)[:200], attempt=attempt)
            settle_until = time.time() + self.settle_s
        self.log("ic_driver_finished", llm_calls=self.llm_calls,
                 elapsed_s=round(time.time() - self.t0, 3))
